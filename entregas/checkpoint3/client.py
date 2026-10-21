"""
client.py – Checkpoint 3: Inserção de Erros e Perdas
=====================================================
Escopo (CP1 + CP2 + CP3):
  - Handshake inicial
  - Fragmentação e envio com janela deslizante (GBN ou SR)
  - Simulação de perda de pacotes (--drop)
  - Simulação de corrupção de pacotes (--error)
  - Detecção de checksum inválido no ACK recebido
  - Retransmissão por timeout (GBN: toda janela; SR: individual)
  - Retransmissão imediata por NACK (SR)
  - Encerramento com FIN / FIN-ACK
"""

import socket
import argparse
import time
import random
import threading
from protocol import (
    Packet,
    FLAG_SYN, FLAG_ACK, FLAG_NACK, FLAG_FIN, FLAG_DATA,
    MODE_GBN, MODE_SR,
    MAX_PAYLOAD_SIZE,
)

TIMEOUT = 2.0   # segundos antes de retransmitir


def receive_loop(sock, state, lock, fragments, server):
    """Thread dedicada a receber ACKs, NACKs e FIN-ACK."""
    sock.settimeout(0.3)
    while state["running"]:
        try:
            data, _ = sock.recvfrom(2048)
            pkt = Packet.from_bytes(data)

            # Ignora ACK corrompido (checksum falhou)
            if pkt.is_corrupted:
                print("[!] ACK recebido com checksum inválido – ignorado (será retransmitido por timeout).")
                continue

            with lock:
                # SYN-ACK
                if pkt.flags == (FLAG_SYN | FLAG_ACK) and state["phase"] == "HANDSHAKE":
                    state["window_size"]   = pkt.window_size
                    state["max_text_size"] = pkt.max_text_size
                    state["phase"]         = "ESTABLISHED"
                    print(f"\n[*] Handshake OK – janela={pkt.window_size} max_text={pkt.max_text_size}")

                # FIN-ACK
                elif pkt.flags == (FLAG_FIN | FLAG_ACK):
                    state["phase"]   = "CLOSED"
                    state["running"] = False
                    print("[*] Conexão encerrada pelo servidor.")

                # NACK (SR: retransmite imediatamente)
                elif pkt.flags & FLAG_NACK:
                    seq = pkt.ack_num
                    print(f"[NACK] Servidor pediu retransmissão imediata de SEQ={seq}")
                    if state["mode"] == MODE_SR and seq not in state["acks"] and fragments:
                        if 0 <= seq < len(fragments):
                            pkt_r = Packet(seq_num=seq, flags=FLAG_DATA,
                                           mode=state["mode"], payload=fragments[seq])
                            sock.sendto(pkt_r.to_bytes(), server)
                            print(f"  [RE-ENVIO NACK] SEQ={seq}")
                            state["timers"][seq] = time.time()

                # ACK de dados
                elif pkt.flags & FLAG_ACK:
                    n = pkt.ack_num
                    print(f"[RECEBIDO] ACK {n}")
                    if state["mode"] == MODE_GBN:
                        if n >= state["base"]:
                            state["base"]       = n + 1
                            state["timer_base"] = time.time()
                    elif state["mode"] == MODE_SR:
                        state["acks"][n] = True
                        while state["base"] in state["acks"]:
                            state["base"] += 1

        except socket.timeout:
            pass
        except Exception as exc:
            if state["running"]:
                print(f"[!] Erro na recepção: {exc}")


def send_pkt(sock, pkt: Packet, server, drop_prob: float, corrupt_prob: float, seq: int):
    """Envia um pacote de dados com simulação de perda e corrupção."""
    if random.random() < drop_prob:
        print(f"  [SIMULAÇÃO] Pacote SEQ={seq} PERDIDO (não enviado)")
        return False
    raw = bytearray(pkt.to_bytes())
    if random.random() < corrupt_prob:
        raw[0] ^= 0xFF   # corrompe o primeiro byte → checksum vai falhar
        print(f"  [SIMULAÇÃO] Pacote SEQ={seq} CORROMPIDO")
        sock.sendto(bytes(raw), server)
        return False
    sock.sendto(bytes(raw), server)
    return True


def main():
    parser = argparse.ArgumentParser(description="Cliente TCD – Checkpoint 3")
    parser.add_argument("--server",  type=str,   default="127.0.0.1")
    parser.add_argument("--port",    type=int,   default=12000)
    parser.add_argument("--mode",    type=str,   choices=["gbn", "sr"], default="gbn")
    parser.add_argument("--drop",    type=float, default=0.0,
                        help="Prob. de perda de pacote (0.0–1.0)")
    parser.add_argument("--error",   type=float, default=0.0,
                        help="Prob. de corrupção de pacote (0.0–1.0)")
    args = parser.parse_args()

    mode   = MODE_GBN if args.mode == "gbn" else MODE_SR
    sock   = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server = (args.server, args.port)

    state = {
        "phase":         "HANDSHAKE",
        "running":       True,
        "mode":          mode,
        "window_size":   1,
        "max_text_size": 30,
        "base":          0,
        "next_seq":      0,
        "acks":          {},
        "timer_base":    time.time(),
        "timers":        {},
    }
    lock = threading.Lock()

    # fragments compartilhado com receive_loop (para NACK SR)
    fragments = []

    recv_thread = threading.Thread(
        target=receive_loop,
        args=(sock, state, lock, fragments, server),
        daemon=True,
    )
    recv_thread.start()

    # ────────────────────────────────────────────────────────────────────────
    # FASE 1: HANDSHAKE
    # ────────────────────────────────────────────────────────────────────────
    print(f"[*] Enviando SYN para {server} (modo={args.mode.upper()})...")
    print(f"    Drop   : {args.drop*100:.0f}%   |   Error: {args.error*100:.0f}%")
    syn = Packet(flags=FLAG_SYN, mode=mode, window_size=0, max_text_size=30)
    sock.sendto(syn.to_bytes(), server)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        with lock:
            if state["phase"] == "ESTABLISHED":
                break
        time.sleep(0.05)

    if state["phase"] != "ESTABLISHED":
        print("[!] Handshake falhou.")
        state["running"] = False
        recv_thread.join()
        sock.close()
        return

    # ────────────────────────────────────────────────────────────────────────
    # FASE 2: ENVIO DE DADOS
    # ────────────────────────────────────────────────────────────────────────
    msg = input(f"\nDigite a mensagem (máx {state['max_text_size']} chars): ")
    if len(msg) > state["max_text_size"]:
        msg = msg[:state["max_text_size"]]
        print(f"[*] Mensagem truncada para: '{msg}'")

    # Preenche a lista compartilhada (para NACK SR na receive_loop)
    frags = [
        msg[i : i + MAX_PAYLOAD_SIZE].encode("utf-8")
        for i in range(0, len(msg), MAX_PAYLOAD_SIZE)
    ]
    fragments.extend(frags)
    total = len(fragments)
    print(f"[*] {total} fragmento(s) para enviar.\n")

    with lock:
        state["timer_base"] = time.time()

    while True:
        with lock:
            if state["base"] >= total:
                break

            win  = state["window_size"]
            base = state["base"]
            nxt  = state["next_seq"]

            # ── Envia pacotes dentro da janela ────────────────────────────
            while nxt < base + win and nxt < total:
                pkt = Packet(
                    seq_num = nxt,
                    flags   = FLAG_DATA,
                    mode    = mode,
                    payload = fragments[nxt],
                )
                sent = send_pkt(sock, pkt, server, args.drop, args.error, nxt)
                if sent:
                    print(f"[ENVIADO] SEQ={nxt} payload='{fragments[nxt].decode()}'")

                if mode == MODE_GBN:
                    if nxt == base:
                        state["timer_base"] = time.time()
                else:
                    state["timers"][nxt] = time.time()

                state["next_seq"] = nxt = nxt + 1

            # ── Verifica timeouts ─────────────────────────────────────────
            now = time.time()

            if mode == MODE_GBN:
                if (now - state["timer_base"]) > TIMEOUT:
                    print(f"[TIMEOUT] GBN – reenviando janela a partir de SEQ={state['base']}...")
                    state["timer_base"] = now
                    for i in range(state["base"], state["next_seq"]):
                        p = Packet(seq_num=i, flags=FLAG_DATA, mode=mode, payload=fragments[i])
                        sock.sendto(p.to_bytes(), server)
                        print(f"  [RE-ENVIO] SEQ={i}")

            else:  # SR
                for seq in range(state["base"], state["next_seq"]):
                    if seq not in state["acks"]:
                        t = state["timers"].get(seq, now)
                        if (now - t) > TIMEOUT:
                            print(f"[TIMEOUT] SR – reenviando SEQ={seq}...")
                            p = Packet(seq_num=seq, flags=FLAG_DATA, mode=mode, payload=fragments[seq])
                            sock.sendto(p.to_bytes(), server)
                            state["timers"][seq] = now

        time.sleep(0.05)

    print("\n[*] Todos os fragmentos confirmados!")

    # ────────────────────────────────────────────────────────────────────────
    # FASE 3: ENCERRAMENTO
    # ────────────────────────────────────────────────────────────────────────
    fin = Packet(seq_num=total, flags=FLAG_FIN, mode=mode)
    sock.sendto(fin.to_bytes(), server)
    print("[*] FIN enviado. Aguardando FIN-ACK...")

    deadline = time.time() + 3.0
    while time.time() < deadline:
        with lock:
            if state["phase"] == "CLOSED":
                break
        time.sleep(0.05)

    state["running"] = False
    recv_thread.join()
    sock.close()
    print("[*] Cliente encerrado.")


if __name__ == "__main__":
    main()
