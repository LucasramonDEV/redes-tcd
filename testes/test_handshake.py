"""
Testes do handshake de 3 vias e do fluxo completo (GBN e SR).

Uso (na raiz do projeto):
    python3 testes/test_handshake.py

Sobe o server.py em uma porta alta, roda clientes reais e sockets crus,
e imprime PASSOU/FALHOU para cada caso. Sai com código 1 se algo falhar.
"""
import os
import socket
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from protocol import (Packet, FLAG_SYN, FLAG_ACK, FLAG_DATA,  # noqa: E402
                      MODE_GBN)

PORTA = 12555
resultados = []


def check(nome, cond, detalhe=""):
    resultados.append(cond)
    print(f"[{'PASSOU' if cond else 'FALHOU'}] {nome}" + (f"  -> {detalhe}" if detalhe and not cond else ""))


def sobe_servidor():
    return subprocess.Popen([sys.executable, "-u", "server.py", "--port", str(PORTA)],
                            cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def para_servidor(srv):
    srv.terminate()
    try:
        out, _ = srv.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        srv.kill()
        out, _ = srv.communicate()
    return out


def roda_cliente(modo, msg, extra=()):
    r = subprocess.run([sys.executable, "-u", "client.py", "--port", str(PORTA), "--mode", modo, *extra],
                       cwd=RAIZ, input=msg + "\n", capture_output=True, text=True, timeout=90)
    return r.stdout + r.stderr


def novo_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.5)
    return s


def recebe(s):
    try:
        data, _ = s.recvfrom(2048)
        return Packet.from_bytes(data)
    except socket.timeout:
        return None


def syn(isn):
    return Packet(seq_num=isn, flags=FLAG_SYN, mode=MODE_GBN, window_size=0, max_text_size=30)


def main():
    srv = sobe_servidor()
    time.sleep(1)
    dest = ("127.0.0.1", PORTA)

    # 1) Fluxo completo com clientes reais, sem erros e com erros simulados
    msg = "Hello World teste 123"
    cenarios = [("gbn", ()), ("sr", ()), ("gbn", ("--drop", "0.3")), ("sr", ("--drop", "0.3")),
                ("gbn", ("--error", "0.3")), ("sr", ("--error", "0.3"))]
    for modo, extra in cenarios:
        out = roda_cliente(modo, msg, extra)
        nome = f"cliente real modo={modo} {' '.join(extra)}".strip()
        check(nome + ": handshake completo", "ACK final enviado" in out and "Handshake completo" in out, out[-400:])
        check(nome + ": encerrou sem traceback", "Traceback" not in out, out[-400:])

    # 2) Falhas no handshake com sockets crus
    # (b) ACK com ack_num errado deve ser ignorado
    s = novo_socket()
    s.sendto(syn(100).to_bytes(), dest)
    sa = recebe(s)
    check("(b) SYN-ACK recebido", sa is not None and sa.flags == (FLAG_SYN | FLAG_ACK))
    if sa:
        check("(b) SYN-ACK confirma ISN_c+1", sa.ack_num == 101)
        s.sendto(Packet(seq_num=101, ack_num=(sa.seq_num + 5) & 0xFFFF, flags=FLAG_ACK).to_bytes(), dest)
        # (c) DATA antes do ACK final: descartado e SYN-ACK reenviado
        s.sendto(Packet(seq_num=0, flags=FLAG_DATA, payload=b"abcd").to_bytes(), dest)
        r = recebe(s)
        check("(c) DATA em SYN_RCVD gera reenvio do SYN-ACK (e nao ACK de dado)",
              r is not None and r.flags == (FLAG_SYN | FLAG_ACK), str(r))
        # (d) SYN duplicado com mesmo ISN reenvia SYN-ACK
        s.sendto(syn(100).to_bytes(), dest)
        r = recebe(s)
        check("(d) SYN duplicado reenvia SYN-ACK",
              r is not None and r.flags == (FLAG_SYN | FLAG_ACK) and r.seq_num == sa.seq_num, str(r))
        # ACK correto, depois DATA aceito
        s.sendto(Packet(seq_num=101, ack_num=(sa.seq_num + 1) & 0xFFFF, flags=FLAG_ACK).to_bytes(), dest)
        time.sleep(0.3)
        s.sendto(Packet(seq_num=0, flags=FLAG_DATA, payload=b"abcd").to_bytes(), dest)
        r = recebe(s)
        check("(c) apos ACK correto, DATA e aceito e confirmado",
              r is not None and r.flags == FLAG_ACK and r.ack_num == 0, str(r))
        # (e) ACK final duplicado em ESTABLISHED nao quebra nada
        s.sendto(Packet(seq_num=101, ack_num=(sa.seq_num + 1) & 0xFFFF, flags=FLAG_ACK).to_bytes(), dest)
        s.sendto(Packet(seq_num=1, flags=FLAG_DATA, payload=b"efgh").to_bytes(), dest)
        r = recebe(s)
        check("(e) ACK duplicado em ESTABLISHED: dados seguintes continuam OK",
              r is not None and r.flags == FLAG_ACK and r.ack_num == 1, str(r))
    s.close()

    # (a) SYN sem ACK final: servidor reenvia SYN-ACK ate abandonar (1 + 5 retries = 6)
    s = novo_socket()
    s.settimeout(1.5)
    s.sendto(syn(200).to_bytes(), dest)
    contagem, fim = 0, time.time() + 9
    while time.time() < fim:
        p = recebe(s)
        if p is not None and p.flags == (FLAG_SYN | FLAG_ACK):
            contagem += 1
    check("(a) servidor reenviou SYN-ACK 6x no total (1 + 5 retries)", contagem == 6, f"contagem={contagem}")
    s.close()

    out = para_servidor(srv)
    check("(a) servidor logou abandono do handshake", "abandonado" in out, out[-500:])
    check("servidor sem traceback", "Traceback" not in out and "Erro no servidor" not in out, out[-500:])
    check("servidor logou ESTABLISHED antes do primeiro DATA do cliente real",
          "ACK final recebido" in out and out.index("ACK final recebido") < out.index("FLAGS=DATA"))
    check("servidor entregou a mensagem completa", msg in out, out[-500:])

    ok = all(resultados)
    print(f"\n{sum(resultados)}/{len(resultados)} verificacoes passaram.")
    print("Nao cobertos aqui: perda de SYN-ACK/ACK final com proxy (teste manual no manual_de_testes.txt).")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
