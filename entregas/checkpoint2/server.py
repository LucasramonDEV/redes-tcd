"""
server.py – Checkpoint 2: Protocolo Sem Erros
==============================================
Escopo (CP1 + CP2):
  - Handshake inicial (SYN / SYN-ACK) trocando modo, janela e max_text
  - Recepção dos fragmentos de dados em canal sem erros e sem perdas
  - Suporte a GBN (aceita só na ordem) e SR (aceita fora de ordem, bufferiza)
  - Envio de ACK para cada fragmento recebido corretamente
  - Encerramento com FIN / FIN-ACK e exibição da mensagem completa
"""

import socket
import argparse
from protocol import (
    Packet,
    FLAG_SYN, FLAG_ACK, FLAG_FIN, FLAG_DATA,
    MODE_GBN, MODE_SR,
)


def main():
    parser = argparse.ArgumentParser(description="Servidor TCD – Checkpoint 2")
    parser.add_argument("--port",     type=int, default=12000, help="Porta UDP")
    parser.add_argument("--window",   type=int, default=5,     help="Tamanho da janela (padrão: 5)")
    parser.add_argument("--max-text", type=int, default=30,    help="Max texto aceito (padrão: 30)")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", args.port))
    print(f"[*] Servidor aguardando na porta {args.port}...")

    # Estado por cliente (suporta múltiplos clientes sequencialmente)
    clients = {}

    while True:
        try:
            data, addr = sock.recvfrom(2048)
            pkt = Packet.from_bytes(data)
            print(f"\n[RECEBIDO de {addr}] {pkt}")

            # ── Inicializa estado do cliente na primeira mensagem ─────────────
            if addr not in clients:
                clients[addr] = {
                    "state":         "CLOSED",
                    "mode":          pkt.mode,
                    "expected_seq":  0,
                    "buffer":        {},   # buffer SR: {seq_num: texto}
                    "received_text": "",
                }
            c = clients[addr]

            # ────────────────────────────────────────────────────────────────
            # HANDSHAKE – SYN
            # ────────────────────────────────────────────────────────────────
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
                sock.sendto(resp.to_bytes(), addr)
                mode_str = "SR" if pkt.mode == MODE_SR else "GBN"
                print(f"[*] Handshake OK – modo={mode_str} janela={args.window} max_text={args.max_text}")

            # ────────────────────────────────────────────────────────────────
            # DADOS
            # ────────────────────────────────────────────────────────────────
            elif (pkt.flags & FLAG_DATA) and c["state"] == "ESTABLISHED":

                # ── Go-Back-N ─────────────────────────────────────────────
                if c["mode"] == MODE_GBN:
                    if pkt.seq_num == c["expected_seq"]:
                        text_part = pkt.payload.decode("utf-8", errors="ignore")
                        c["received_text"] += text_part
                        c["expected_seq"]  += 1
                        print(f"[GBN] Fragmento {pkt.seq_num} entregue: '{text_part}'")

                        ack = Packet(ack_num=pkt.seq_num, flags=FLAG_ACK)
                        sock.sendto(ack.to_bytes(), addr)
                    else:
                        # Fora de ordem: reenvia o último ACK válido
                        print(f"[GBN] Fora de ordem – esperava {c['expected_seq']}, chegou {pkt.seq_num}.")
                        last_ack = c["expected_seq"] - 1
                        if last_ack >= 0:
                            ack = Packet(ack_num=last_ack, flags=FLAG_ACK)
                            sock.sendto(ack.to_bytes(), addr)

                # ── Selective Repeat ──────────────────────────────────────
                elif c["mode"] == MODE_SR:
                    win = args.window
                    if c["expected_seq"] <= pkt.seq_num < c["expected_seq"] + win:
                        if pkt.seq_num not in c["buffer"]:
                            c["buffer"][pkt.seq_num] = pkt.payload.decode("utf-8", errors="ignore")
                            print(f"[SR] Fragmento {pkt.seq_num} bufferizado.")

                        # ACK individual
                        ack = Packet(ack_num=pkt.seq_num, flags=FLAG_ACK)
                        sock.sendto(ack.to_bytes(), addr)

                        # Avança janela (entrega sequencial ao buffer superior)
                        while c["expected_seq"] in c["buffer"]:
                            c["received_text"] += c["buffer"].pop(c["expected_seq"])
                            print(f"[SR] Janela avançou → esperado agora: {c['expected_seq'] + 1}")
                            c["expected_seq"] += 1

                    elif pkt.seq_num < c["expected_seq"]:
                        # Duplicata – confirma novamente
                        ack = Packet(ack_num=pkt.seq_num, flags=FLAG_ACK)
                        sock.sendto(ack.to_bytes(), addr)

            # ────────────────────────────────────────────────────────────────
            # ENCERRAMENTO – FIN
            # ────────────────────────────────────────────────────────────────
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
