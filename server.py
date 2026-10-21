import socket
import argparse
import random
import time
from protocol import *

# Parâmetros do handshake de 3 vias (SYN -> SYN-ACK -> ACK)
SYNACK_TIMEOUT = 1.0      # segundos até reenviar o SYN-ACK sem ACK de volta
SYNACK_MAX_RETRIES = 5    # após isso, abandona a conexão semiaberta
WINDOW_SIZE = 5           # janela definida pelo servidor


def send_syn_ack(server_socket, client_address, client):
    """Envia (ou reenvia) o SYN-ACK: seq = ISN do servidor, ack = ISN do cliente + 1."""
    syn_ack = Packet(
        seq_num=client["server_isn"],
        ack_num=(client["client_isn"] + 1) & 0xFFFF,
        flags=FLAG_SYN | FLAG_ACK,
        mode=client["mode"],
        window_size=WINDOW_SIZE,
        max_text_size=client["max_text"]
    )
    server_socket.sendto(syn_ack.to_bytes(), client_address)
    client["syn_ack_time"] = time.time()


def retransmit_pending_syn_acks(server_socket, clients):
    """Timer do handshake: reenvia SYN-ACK para conexões em SYN_RCVD sem ACK final."""
    now = time.time()
    for client_address, client in clients.items():
        if client["state"] != "SYN_RCVD":
            continue
        if now - client["syn_ack_time"] < SYNACK_TIMEOUT:
            continue
        if client["retries"] >= SYNACK_MAX_RETRIES:
            print(f"[!] Handshake com {client_address} abandonado: ACK final nunca chegou.")
            client["state"] = "CLOSED"
            continue
        client["retries"] += 1
        print(f"[TIMEOUT] ACK final de {client_address} não chegou. "
              f"Reenviando SYN-ACK (tentativa {client['retries']}/{SYNACK_MAX_RETRIES}).")
        send_syn_ack(server_socket, client_address, client)


def main():
    parser = argparse.ArgumentParser(description="Servidor TCD (Transporte Confiável de Dados)")
    parser.add_argument("--port", type=int, default=12000, help="Porta do servidor")
    args = parser.parse_args()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(('', args.port))
    # Timeout curto para que o timer do handshake (SYN-ACK) possa ser verificado
    server_socket.settimeout(0.5)

    print(f"[*] Servidor iniciado na porta {args.port}. Aguardando conexões...")

    clients = {}

    while True:
        try:
            retransmit_pending_syn_acks(server_socket, clients)

            try:
                data, client_address = server_socket.recvfrom(2048)
            except socket.timeout:
                continue
            pkt = Packet.from_bytes(data)

            print(f"\n[RECEBIDO de {client_address}] {pkt}")

            if pkt.is_corrupted:
                print(f"[!] Pacote corrompido! Ignorando (ou enviando NACK se SR).")

                # NACK explicitly supported as per SR mode specification
                if client_address in clients and clients[client_address]["state"] == "ESTABLISHED" \
                        and clients[client_address]["mode"] == MODE_SR:
                    nack_pkt = Packet(
                        ack_num=pkt.seq_num,
                        flags=FLAG_NACK
                    )
                    server_socket.sendto(nack_pkt.to_bytes(), client_address)

                continue

            # Máquina de estados simples por cliente
            if client_address not in clients:
                clients[client_address] = {
                    "state": "CLOSED",
                    "expected_seq": 0,
                    "mode": pkt.mode,
                    "window_size": WINDOW_SIZE, # Servidor define janela
                    "max_text": pkt.max_text_size,
                    "buffer": {}, # Para SR
                    "received_text": "",
                    # Controle do handshake de 3 vias
                    "client_isn": None,
                    "server_isn": 0,
                    "syn_ack_time": 0,
                    "retries": 0
                }

            client = clients[client_address]

            # ---------------- HANDSHAKE (3 vias) ----------------
            # Passo 1: cliente -> SYN
            if pkt.flags & FLAG_SYN:
                same_syn = client["client_isn"] == pkt.seq_num

                if client["state"] == "SYN_RCVD" and same_syn:
                    # SYN retransmitido: nosso SYN-ACK provavelmente se perdeu
                    print("[*] SYN duplicado em SYN_RCVD. Reenviando SYN-ACK.")
                    send_syn_ack(server_socket, client_address, client)
                elif client["state"] == "ESTABLISHED" and same_syn:
                    # SYN atrasado de uma conexão que já foi confirmada com ACK: ignora
                    print("[*] SYN duplicado/atrasado em ESTABLISHED. Ignorando.")
                else:
                    # Nova tentativa de conexão: vai para SYN_RCVD, e NÃO para ESTABLISHED.
                    # A conexão só é considerada aberta quando o ACK final chegar.
                    client["state"] = "SYN_RCVD"
                    client["client_isn"] = pkt.seq_num
                    client["server_isn"] = random.randint(0, 0xFFFE)
                    client["mode"] = pkt.mode
                    client["max_text"] = pkt.max_text_size
                    client["expected_seq"] = 0
                    client["received_text"] = ""
                    client["buffer"].clear()
                    client["retries"] = 0

                    send_syn_ack(server_socket, client_address, client)
                    print(f"[*] SYN recebido. Estado = SYN_RCVD. SYN-ACK enviado, aguardando ACK final...")
                continue

            # Passo 3: cliente -> ACK (confirma o SYN-ACK). Só aqui a conexão é estabelecida.
            if client["state"] == "SYN_RCVD":
                if pkt.flags == FLAG_ACK:
                    expected_seq = (client["client_isn"] + 1) & 0xFFFF
                    expected_ack = (client["server_isn"] + 1) & 0xFFFF
                    if pkt.seq_num == expected_seq and pkt.ack_num == expected_ack:
                        client["state"] = "ESTABLISHED"
                        print(f"[*] ACK final recebido. Handshake completado! Estado = ESTABLISHED "
                              f"(modo={'SR' if client['mode'] == MODE_SR else 'GBN'}, janela={WINDOW_SIZE}).")
                    else:
                        print(f"[!] ACK de handshake inválido (seq={pkt.seq_num}, ack={pkt.ack_num}; "
                              f"esperado seq={expected_seq}, ack={expected_ack}). Ignorando.")
                elif pkt.flags & FLAG_DATA:
                    # Cliente já se considera conectado: nosso SYN-ACK ou o ACK dele se perdeu.
                    print("[*] DATA recebido antes do ACK final. Descartando e reenviando SYN-ACK.")
                    send_syn_ack(server_socket, client_address, client)
                continue

            # Tratamento de Dados
            if pkt.flags & FLAG_DATA and client["state"] == "ESTABLISHED":

                # Simulação de Atraso e Perda (pode ser ajustado)
                # if random.random() < 0.1:
                #    print(f"[x] ERRO SIMULADO: Pacote {pkt.seq_num} 'perdido' na rede.")
                #    continue

                if client["mode"] == MODE_GBN:
                    # GBN: Aceita apenas na ordem correta
                    if pkt.seq_num == client["expected_seq"]:
                        text_part = pkt.payload.decode('utf-8', errors='ignore')
                        client["received_text"] += text_part
                        print(f"[*] GBN: Entregue fragmento '{text_part}'. Esperado agora: {pkt.seq_num + 1}")

                        ack_pkt = Packet(
                            ack_num=pkt.seq_num,
                            flags=FLAG_ACK
                        )
                        server_socket.sendto(ack_pkt.to_bytes(), client_address)
                        client["expected_seq"] += 1
                    else:
                        print(f"[*] GBN: Fora de ordem. Esperava {client['expected_seq']}, recebeu {pkt.seq_num}. Reenviando ACK {client['expected_seq'] - 1}")
                        # Reenvia último ACK (Go-Back-N clássico)
                        if client["expected_seq"] > 0:
                            ack_pkt = Packet(
                                ack_num=client["expected_seq"] - 1,
                                flags=FLAG_ACK
                            )
                            server_socket.sendto(ack_pkt.to_bytes(), client_address)

                elif client["mode"] == MODE_SR:
                    # Selective Repeat: Aceita pacotes fora de ordem na janela
                    if client["expected_seq"] <= pkt.seq_num < client["expected_seq"] + client["window_size"]:
                        if pkt.seq_num not in client["buffer"]:
                            client["buffer"][pkt.seq_num] = pkt.payload.decode('utf-8', errors='ignore')
                            print(f"[*] SR: Fragmento {pkt.seq_num} bufferizado.")

                        # SR envia ACK individual
                        ack_pkt = Packet(
                            ack_num=pkt.seq_num,
                            flags=FLAG_ACK
                        )
                        server_socket.sendto(ack_pkt.to_bytes(), client_address)

                        # Desliza a janela se puder
                        while client["expected_seq"] in client["buffer"]:
                            client["received_text"] += client["buffer"].pop(client["expected_seq"])
                            client["expected_seq"] += 1
                            print(f"[*] SR: Janela avançou para {client['expected_seq']}")
                    else:
                        # Se já recebeu (está atrás), apenas confirma
                        if pkt.seq_num < client["expected_seq"]:
                            ack_pkt = Packet(ack_num=pkt.seq_num, flags=FLAG_ACK)
                            server_socket.sendto(ack_pkt.to_bytes(), client_address)

            # Encerramento
            elif pkt.flags & FLAG_FIN and client["state"] == "ESTABLISHED":
                print(f"[*] Recebido pedido de FIN.")
                print(f"==== MENSAGEM FINAL RECEBIDA ====\n{client['received_text']}\n=================================")

                ack_pkt = Packet(
                    ack_num=pkt.seq_num,
                    flags=FLAG_FIN | FLAG_ACK
                )
                server_socket.sendto(ack_pkt.to_bytes(), client_address)
                client["state"] = "CLOSED"

        except KeyboardInterrupt:
            print("\nEncerrando servidor...")
            break
        except Exception as e:
            print(f"[!] Erro no servidor: {e}")

if __name__ == "__main__":
    main()
