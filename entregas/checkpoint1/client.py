"""
client.py – Checkpoint 1: Handshake & Sockets
==============================================
Escopo: conectar ao servidor via UDP e realizar o handshake inicial,
trocando modo de operação, tamanho da janela e tamanho máximo do texto.
"""

import socket
import argparse
import time
from protocol import Packet, FLAG_SYN, FLAG_ACK, MODE_GBN, MODE_SR


def main():
    parser = argparse.ArgumentParser(description="Cliente TCD – Checkpoint 1")
    parser.add_argument("--server", type=str, default="127.0.0.1",
                        help="IP do servidor")
    parser.add_argument("--port",   type=int, default=12000,
                        help="Porta UDP do servidor")
    parser.add_argument("--mode",   type=str, choices=["gbn", "sr"], default="gbn",
                        help="Modo de operação: gbn (Go-Back-N) ou sr (Selective Repeat)")
    parser.add_argument("--max-text", type=int, default=30,
                        help="Tamanho máximo do texto que o cliente sugere (padrão: 30)")
    args = parser.parse_args()

    mode = MODE_GBN if args.mode == "gbn" else MODE_SR

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)   # aguarda resposta por até 3 segundos
    server_addr = (args.server, args.port)

    # ── Envio do SYN ──────────────────────────────────────────────────────────
    syn = Packet(
        flags         = FLAG_SYN,
        mode          = mode,
        window_size   = 0,              # cliente não define janela; servidor decide
        max_text_size = args.max_text,  # sugestão do cliente
    )
    print(f"[*] Enviando SYN para {server_addr}...")
    print(f"    Modo solicitado    : {args.mode.upper()}")
    print(f"    Max texto sugerido : {args.max_text} bytes")
    sock.sendto(syn.to_bytes(), server_addr)

    # ── Aguarda SYN-ACK ───────────────────────────────────────────────────────
    try:
        data, _ = sock.recvfrom(1024)
        resp = Packet.from_bytes(data)
        print(f"\n[RECEBIDO] {resp}")

        if resp.flags == (FLAG_SYN | FLAG_ACK):
            mode_str = "SR" if resp.mode == MODE_SR else "GBN"
            print("\n[*] Handshake concluído com sucesso!")
            print(f"    Modo confirmado    : {mode_str}")
            print(f"    Janela definida    : {resp.window_size}")
            print(f"    Max texto aceito   : {resp.max_text_size} bytes")
        else:
            print("[!] Resposta inesperada do servidor.")

    except socket.timeout:
        print("[!] Timeout: servidor não respondeu ao SYN.")

    sock.close()


if __name__ == "__main__":
    main()
