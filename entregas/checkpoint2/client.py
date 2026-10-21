"""
client.py – Checkpoint 2: Protocolo Sem Erros
==============================================
Escopo (CP1 + CP2):
  - Handshake inicial (SYN / SYN-ACK)
  - Fragmentação da mensagem em pedaços de <= 4 bytes
  - Envio com janela deslizante (GBN ou SR) sem simulação de erros
  - Retransmissão por timeout (canal sem erros, mas timeout por segurança)
  - Encerramento com FIN / FIN-ACK
"""

import socket
import argparse
import time
import threading
from protocol import (
    Packet,
    FLAG_SYN, FLAG_ACK, FLAG_FIN, FLAG_DATA,
    MODE_GBN, MODE_SR,
    MAX_PAYLOAD_SIZE,
)

TIMEOUT = 2.0   # segundos antes de retransmitir


def receive_loop(sock, state, lock):
    """Thread dedicada a receber ACKs e FIN-ACK do servidor."""
    sock.settimeout(0.3)
    while state["running"]:
        try:
            data, _ = sock.recvfrom(2048)
            pkt = Packet.from_bytes(data)

            with lock:
                # ── SYN-ACK (handshake) ──────────────────────────────────
                if pkt.flags == (FLAG_SYN | FLAG_ACK) and state["phase"] == "HANDSHAKE":
                    state["window_size"]   = pkt.window_size
                    state["max_text_size"] = pkt.max_text_size
                    state["phase"]         = "ESTABLISHED"
                    print(f"\n[*] Handshake OK – janela={pkt.window_size} max_text={pkt.max_text_size}")

                # ── FIN-ACK (encerramento) ───────────────────────────────
                elif pkt.flags == (FLAG_FIN | FLAG_ACK):
                    state["phase"]   = "CLOSED"
                    state["running"] = False
                    print("[*] Conexão encerrada pelo servidor.")

                # ── ACK de dados ──────────────────────────────────────────
                elif pkt.flags & FLAG_ACK:
                    n = pkt.ack_num
                    print(f"[RECEBIDO] ACK {n}")

                    if state["mode"] == MODE_GBN:
                        # ACK cumulativo: confirma tudo até n
                        if n >= state["base"]:
                            state["base"] = n + 1
                            state["timer_base"] = time.time()

                    elif state["mode"] == MODE_SR:
                        # ACK individual
                        state["acks"][n] = True
                        # Desliza a base
                        while state["base"] in state["acks"]:
                            state["base"] += 1

        except socket.timeout:
            pass
        except Exception as exc:
            if state["running"]:
                print(f"[!] Erro na recepção: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Cliente TCD – Checkpoint 2")
    parser.add_argument("--server",   type=str, default="127.0.0.1")
    parser.add_argument("--port",     type=int, default=12000)
    parser.add_argument("--mode",     type=str, choices=["gbn", "sr"], default="gbn")
    args = parser.parse_args()

    mode = MODE_GBN if args.mode == "gbn" else MODE_SR
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server = (args.server, args.port)

    state = {
        "phase":         "HANDSHAKE",
        "running":       True,
        "mode":          mode,
        "window_size":   1,
        "max_text_size": 30,
        "base":          0,
        "next_seq":      0,
        "acks":          {},          # SR: {seq_num: True}
        "timer_base":    time.time(), # GBN: timer da base da janela
        "timers":        {},          # SR: {seq_num: timestamp}
    }
    lock = threading.Lock()

    # ── Inicia thread de recepção ─────────────────────────────────────────────
    recv_thread = threading.Thread(target=receive_loop, args=(sock, state, lock), daemon=True)
    recv_thread.start()

    # ────────────────────────────────────────────────────────────────────────
    # FASE 1: HANDSHAKE
    # ────────────────────────────────────────────────────────────────────────
    print(f"[*] Enviando SYN para {server} (modo={args.mode.upper()})...")
    syn = Packet(flags=FLAG_SYN, mode=mode, window_size=0, max_text_size=30)
    sock.sendto(syn.to_bytes(), server)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        with lock:
            if state["phase"] == "ESTABLISHED":
                break
        time.sleep(0.05)

    if state["phase"] != "ESTABLISHED":
        print("[!] Handshake falhou. Encerrando.")
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

    fragments = [
        msg[i : i + MAX_PAYLOAD_SIZE].encode("utf-8")
        for i in range(0, len(msg), MAX_PAYLOAD_SIZE)
    ]
    total = len(fragments)
    print(f"[*] {total} fragmento(s) para enviar.\n")

    with lock:
        state["timer_base"] = time.time()

    while True:
        with lock:
            if state["base"] >= total:
                break   # todos confirmados

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
                sock.sendto(pkt.to_bytes(), server)
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
                    print(f"[TIMEOUT] GBN – reenviando janela a partir de {state['base']}...")
                    state["timer_base"] = now
                    for i in range(state["base"], state["next_seq"]):
                        pkt = Packet(seq_num=i, flags=FLAG_DATA, mode=mode, payload=fragments[i])
                        sock.sendto(pkt.to_bytes(), server)
                        print(f"  [RE-ENVIO] SEQ={i}")

            else:  # SR
                for seq in range(state["base"], state["next_seq"]):
                    if seq not in state["acks"]:
                        t = state["timers"].get(seq, now)
                        if (now - t) > TIMEOUT:
                            print(f"[TIMEOUT] SR – reenviando SEQ={seq}...")
                            pkt = Packet(seq_num=seq, flags=FLAG_DATA, mode=mode, payload=fragments[seq])
                            sock.sendto(pkt.to_bytes(), server)
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
