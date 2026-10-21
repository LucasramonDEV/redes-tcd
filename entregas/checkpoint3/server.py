"""
server.py – Checkpoint 3: Inserção de Erros e Perdas
=====================================================
Escopo (CP1 + CP2 + CP3):
  - Handshake inicial
  - Recepção com GBN e SR
  - Detecção de corrupção via checksum (descarta ou envia NACK)
  - Simulação de perda de ACK (--drop-ack)
  - Simulação de corrupção de ACK (--corrupt-ack)
  - Exibição de todos os casos do protocolo
"""

import socket
import argparse
import random
from protocol import (
    Packet,
    FLAG_SYN, FLAG_ACK, FLAG_NACK, FLAG_FIN, FLAG_DATA,
    MODE_GBN, MODE_SR,
)


def send(sock, pkt: Packet, addr, drop_prob: float, corrupt_prob: float):
    """Envia um pacote com simulação de perda e corrupção no lado do servidor."""
    if random.random() < drop_prob:
        print(f"  [SIMULAÇÃO] ACK/NACK {pkt.ack_num} PERDIDO (não enviado)")
        return
    raw = bytearray(pkt.to_bytes())
    if random.random() < corrupt_prob:
        raw[0] ^= 0xFF   # inverte bits do primeiro byte → checksum vai falhar
        print(f"  [SIMULAÇÃO] ACK/NACK {pkt.ack_num} CORROMPIDO")
    sock.sendto(bytes(raw), addr)


def main():
    parser = argparse.ArgumentParser(description="Servidor TCD – Checkpoint 3")
    parser.add_argument("--port",        type=int,   default=12000)
    parser.add_argument("--window",      type=int,   default=5)
    parser.add_argument("--max-text",    type=int,   default=30)
    parser.add_argument("--drop-ack",    type=float, default=0.0,
                        help="Prob. de perda de ACK simulada (0.0–1.0)")
    parser.add_argument("--corrupt-ack", type=float, default=0.0,
                        help="Prob. de corrupção de ACK simulada (0.0–1.0)")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", args.port))
    print(f"[*] Servidor aguardando na porta {args.port}...")
    print(f"    Janela       : {args.window}")
    print(f"    Max texto    : {args.max_text}")
    print(f"    Drop ACK     : {args.drop_ack*100:.0f}%")
    print(f"    Corrupt ACK  : {args.corrupt_ack*100:.0f}%\n")

    clients = {}

    while True:
        try:
            data, addr = sock.recvfrom(2048)
            pkt = Packet.from_bytes(data)
            print(f"[RECEBIDO de {addr}] {pkt}")

            # ── Inicializa estado do cliente ──────────────────────────────
            if addr not in clients:
                clients[addr] = {
                    "state":         "CLOSED",
                    "mode":          pkt.mode,
                    "expected_seq":  0,
                    "buffer":        {},
                    "received_text": "",
                }
            c = clients[addr]

            # ── Corrupção detectada ───────────────────────────────────────
            if pkt.is_corrupted:
                print(f"  [!] Pacote CORROMPIDO (checksum inválido).")
                if c.get("state") == "ESTABLISHED" and c["mode"] == MODE_SR:
                    nack = Packet(ack_num=pkt.seq_num, flags=FLAG_NACK)
                    send(sock, nack, addr, args.drop_ack, args.corrupt_ack)
                    print(f"  [SR] NACK {pkt.seq_num} enviado.")
                else:
                    print(f"  [GBN] Pacote descartado – cliente vai reenviar pela janela.")
                continue

            # ────────────────────────────────────────────────────────────
            # HANDSHAKE
            # ────────────────────────────────────────────────────────────
            if pkt.flags & FLAG_SYN:
                c["state"]         = "ESTABLISHED"
                c["mode"]          = pkt.mode
                c["expected_seq"]  = 0
                c["buffer"]        = {}
                c["received_text"] = ""

                resp = Packet(
                    flags         = FLAG_SYN | FLAG_ACK,
                    mode          = pkt.mode,
                    window_size   = args.window,
                    max_text_size = args.max_text,
                )
                sock.sendto(resp.to_bytes(), addr)   # handshake nunca é dropado
                mode_str = "SR" if pkt.mode == MODE_SR else "GBN"
                print(f"  [*] Handshake OK – modo={mode_str} janela={args.window}")

            # ────────────────────────────────────────────────────────────
            # DADOS
            # ────────────────────────────────────────────────────────────
            elif (pkt.flags & FLAG_DATA) and c["state"] == "ESTABLISHED":

                if c["mode"] == MODE_GBN:
                    if pkt.seq_num == c["expected_seq"]:
                        text_part = pkt.payload.decode("utf-8", errors="ignore")
                        c["received_text"] += text_part
                        c["expected_seq"]  += 1
                        print(f"  [GBN] Fragmento {pkt.seq_num} entregue: '{text_part}'")
                        ack = Packet(ack_num=pkt.seq_num, flags=FLAG_ACK)
                        send(sock, ack, addr, args.drop_ack, args.corrupt_ack)
                    else:
                        print(f"  [GBN] Fora de ordem – esperava {c['expected_seq']}, recebeu {pkt.seq_num}. Descartando.")
                        last = c["expected_seq"] - 1
                        if last >= 0:
                            ack = Packet(ack_num=last, flags=FLAG_ACK)
                            send(sock, ack, addr, args.drop_ack, args.corrupt_ack)

                elif c["mode"] == MODE_SR:
                    win = args.window
                    if c["expected_seq"] <= pkt.seq_num < c["expected_seq"] + win:
                        if pkt.seq_num not in c["buffer"]:
                            c["buffer"][pkt.seq_num] = pkt.payload.decode("utf-8", errors="ignore")
                            print(f"  [SR] Fragmento {pkt.seq_num} bufferizado.")
                        ack = Packet(ack_num=pkt.seq_num, flags=FLAG_ACK)
                        send(sock, ack, addr, args.drop_ack, args.corrupt_ack)

                        while c["expected_seq"] in c["buffer"]:
                            c["received_text"] += c["buffer"].pop(c["expected_seq"])
                            print(f"  [SR] Janela avançou → esperado: {c['expected_seq'] + 1}")
                            c["expected_seq"] += 1

                    elif pkt.seq_num < c["expected_seq"]:
                        ack = Packet(ack_num=pkt.seq_num, flags=FLAG_ACK)
                        send(sock, ack, addr, args.drop_ack, args.corrupt_ack)

            # ────────────────────────────────────────────────────────────
            # ENCERRAMENTO
            # ────────────────────────────────────────────────────────────
            elif pkt.flags & FLAG_FIN:
                print(f"\n{'='*40}")
                print(f"MENSAGEM COMPLETA RECEBIDA:")
                print(f"  '{c['received_text']}'")
                print(f"{'='*40}\n")
                fin_ack = Packet(ack_num=pkt.seq_num, flags=FLAG_FIN | FLAG_ACK)
                sock.sendto(fin_ack.to_bytes(), addr)
                c["state"] = "CLOSED"

        except KeyboardInterrupt:
            print("\n[*] Servidor encerrado.")
            break
        except Exception as exc:
            print(f"[!] Erro: {exc}")

    sock.close()


if __name__ == "__main__":
    main()
