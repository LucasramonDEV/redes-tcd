"""
server.py – Checkpoint 1: Handshake & Sockets
==============================================
Escopo: receber conexão do cliente via UDP, realizar o handshake inicial
trocando modo de operação, tamanho da janela e tamanho máximo do texto.
"""

import socket
import argparse
from protocol import Packet, FLAG_SYN, FLAG_ACK, MODE_GBN, MODE_SR


def main():
    parser = argparse.ArgumentParser(description="Servidor TCD – Checkpoint 1")
    parser.add_argument("--port",        type=int, default=12000,
                        help="Porta UDP em que o servidor vai escutar")
    parser.add_argument("--window",      type=int, default=5,
                        help="Tamanho da janela definido pelo servidor (padrão: 5)")
    parser.add_argument("--max-text",    type=int, default=30,
                        help="Tamanho máximo do texto aceito (padrão: 30 bytes)")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", args.port))
    print(f"[*] Servidor aguardando na porta {args.port}...")
    print(f"    Janela configurada : {args.window}")
    print(f"    Max texto          : {args.max_text} bytes")

    while True:
        try:
            data, client_addr = sock.recvfrom(1024)
            pkt = Packet.from_bytes(data)
            print(f"\n[RECEBIDO de {client_addr}] {pkt}")

            # ── Handshake: SYN recebido → responde SYN-ACK ──────────────────
            if pkt.flags & FLAG_SYN:
                mode_str = "SR" if pkt.mode == MODE_SR else "GBN"
                print(f"[*] Handshake iniciado pelo cliente.")
                print(f"    Modo solicitado    : {mode_str}")
                print(f"    Max texto (cliente): {pkt.max_text_size} bytes")

                # Servidor confirma e informa janela + max_text ao cliente
                resp = Packet(
                    flags         = FLAG_SYN | FLAG_ACK,
                    mode          = pkt.mode,          # ecoa o modo do cliente
                    window_size   = args.window,        # servidor define a janela
                    max_text_size = args.max_text,      # servidor define o limite
                )
                sock.sendto(resp.to_bytes(), client_addr)
                print(f"[ENVIADO  para {client_addr}] {resp}")
                print("[*] Handshake concluído com sucesso!\n")

        except KeyboardInterrupt:
            print("\n[*] Servidor encerrado.")
            break
        except Exception as exc:
            print(f"[!] Erro: {exc}")

    sock.close()


if __name__ == "__main__":
    main()
