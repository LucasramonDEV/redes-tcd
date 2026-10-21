import socket
import argparse
import time
import math
import threading
import random
from protocol import *

HANDSHAKE_TIMEOUT = 1.0   # segundos de espera pelo SYN-ACK antes de reenviar o SYN
HANDSHAKE_RETRIES = 4     # número total de tentativas de SYN

def send_handshake_ack(sock, server_addr, client_state):
    """Passo 3 do handshake: ACK final que confirma o SYN-ACK do servidor."""
    ack_pkt = Packet(
        seq_num=(client_state["client_isn"] + 1) & 0xFFFF,
        ack_num=(client_state["server_isn"] + 1) & 0xFFFF,
        flags=FLAG_ACK,
        mode=client_state["mode"],
        window_size=client_state["window_size"],
        max_text_size=client_state["max_text_size"]
    )
    sock.sendto(ack_pkt.to_bytes(), server_addr)

def receive_loop(sock, client_state, lock):
    sock.settimeout(0.5)
    while client_state["running"]:
        try:
            data, server_address = sock.recvfrom(2048)
            pkt = Packet.from_bytes(data)
            
            if pkt.is_corrupted:
                continue
                
            with lock:
                # Tratamento de Handshake (passo 2 -> passo 3 do 3-way handshake)
                if pkt.flags == (FLAG_SYN | FLAG_ACK):
                    expected_ack = (client_state["client_isn"] + 1) & 0xFFFF
                    if pkt.ack_num != expected_ack:
                        print(f"[!] SYN-ACK inválido (ack={pkt.ack_num}, esperado={expected_ack}). Ignorando.")
                    elif client_state["state"] == "SYN_SENT":
                        client_state["state"] = "ESTABLISHED"
                        client_state["window_size"] = pkt.window_size # Servidor define (deve ser 5)
                        client_state["max_text_size"] = pkt.max_text_size
                        client_state["server_isn"] = pkt.seq_num
                        # ACK final: confirma o SYN-ACK do servidor (seq = ISN_c + 1, ack = ISN_s + 1)
                        send_handshake_ack(sock, server_address, client_state)
                        print(f"\n[*] SYN-ACK recebido. ACK final enviado. Handshake completo! "
                              f"Janela: {pkt.window_size}, Max Texto: {pkt.max_text_size}")
                    elif client_state["state"] == "ESTABLISHED":
                        # SYN-ACK duplicado: o servidor não recebeu nosso ACK final. Reenvia.
                        print("[*] SYN-ACK duplicado recebido. Reenviando ACK final.")
                        send_handshake_ack(sock, server_address, client_state)

                # Tratamento de NACK (SR Mode)
                elif pkt.flags & FLAG_NACK:
                    print(f"\n[RECEBIDO] NACK: {pkt.ack_num}")
                    if client_state["mode"] == MODE_SR:
                        # SR Mode retransmite o pacote NACK'ed imediatamente
                        if pkt.ack_num not in client_state["acks"]:
                            print(f"[*] Reenviando por NACK imediato o pacote {pkt.ack_num}")
                            # Nota: Não temos acesso a `fragments` diretamente nesta thread isolada de maneira limpa,
                            # então forçamos o timeout ajustando o timer do respectivo pacote para estourar na próxima checagem
                            if pkt.ack_num in client_state["timers"]:
                                client_state["timers"][pkt.ack_num] = 0

                # Tratamento de ACKs de dados
                elif pkt.flags & FLAG_ACK and not (pkt.flags & FLAG_SYN):
                    print(f"\n[RECEBIDO] ACK: {pkt.ack_num}")
                    
                    if client_state["mode"] == MODE_GBN:
                        # GBN: ACK cumulativo (confirma todos até ack_num)
                        if pkt.ack_num >= client_state["base"]:
                            client_state["base"] = pkt.ack_num + 1
                    
                    elif client_state["mode"] == MODE_SR:
                        # SR: ACK individual
                        client_state["acks"][pkt.ack_num] = True
                        # Tenta avançar a janela (base)
                        while client_state["base"] in client_state["acks"]:
                            client_state["base"] += 1
                
                # Tratamento de FIN ACK
                if pkt.flags == (FLAG_FIN | FLAG_ACK):
                    client_state["state"] = "CLOSED"
                    client_state["running"] = False
                    print("[*] Conexão encerrada pelo servidor com sucesso.")
                    
        except socket.timeout:
            pass
        except Exception as e:
            if client_state["running"]:
                print(f"[!] Erro ao receber pacote: {e}")

def main():
    parser = argparse.ArgumentParser(description="Cliente TCD (Transporte Confiável de Dados)")
    parser.add_argument("--server", type=str, default="127.0.0.1", help="IP do Servidor")
    parser.add_argument("--port", type=int, default=12000, help="Porta do Servidor")
    parser.add_argument("--mode", type=str, choices=["gbn", "sr"], default="gbn", help="Modo de operação (Go-Back-N ou Selective Repeat)")
    parser.add_argument("--error", type=float, default=0.0, help="Probabilidade de erro (corrupção) simulada no cliente (0.0 a 1.0)")
    parser.add_argument("--drop", type=float, default=0.0, help="Probabilidade de perda de pacote simulada no cliente (0.0 a 1.0)")
    args = parser.parse_args()
    
    mode = MODE_GBN if args.mode == "gbn" else MODE_SR
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_addr = (args.server, args.port)
    
    client_state = {
        "state": "CLOSED",
        "running": True,
        "mode": mode,
        "window_size": 1, # Será atualizado pelo server
        "max_text_size": 30, # Default exigido
        "base": 0,
        "next_seq_num": 0,
        "acks": {}, # Para SR
        "timers": {}, # Timers individuais por pacote (SR) ou timer único (GBN)
        "client_isn": random.randint(0, 0xFFFE), # Número de sequência inicial do handshake
        "server_isn": 0
    }
    
    lock = threading.Lock()
    recv_thread = threading.Thread(target=receive_loop, args=(sock, client_state, lock))
    recv_thread.start()
    
    try:
        # FASE 1: HANDSHAKE
        print("[*] Iniciando Handshake...")
        syn_pkt = Packet(
            seq_num=client_state["client_isn"],
            flags=FLAG_SYN,
            mode=mode,
            window_size=0, # Enviando 0, esperando servidor setar 5
            max_text_size=client_state["max_text_size"]
        )

        with lock:
            client_state["state"] = "SYN_SENT"

        # Passo 1: SYN (com retransmissão caso o SYN ou o SYN-ACK se percam)
        established = False
        for attempt in range(1, HANDSHAKE_RETRIES + 1):
            sock.sendto(syn_pkt.to_bytes(), server_addr)
            print(f"[*] SYN enviado (tentativa {attempt}/{HANDSHAKE_RETRIES}). Aguardando SYN-ACK...")

            # Passo 2: aguarda SYN-ACK (a receive_loop envia o ACK final, passo 3)
            deadline = time.time() + HANDSHAKE_TIMEOUT
            while time.time() < deadline:
                with lock:
                    if client_state["state"] == "ESTABLISHED":
                        established = True
                        break
                time.sleep(0.05)
            if established:
                break

        if not established:
            print("[!] Falha no handshake. Servidor não respondeu.")
            client_state["running"] = False
            recv_thread.join()
            return
            
        # FASE 2: ENVIO DA MENSAGEM
        message = input(f"Digite a mensagem (máx {client_state['max_text_size']} chars): ")
        if len(message) > client_state["max_text_size"]:
            message = message[:client_state["max_text_size"]]
            print(f"[*] Mensagem truncada para: {message}")
            
        # Fragmentação (payload <= 4 chars)
        fragments = [message[i:i+MAX_PAYLOAD_SIZE].encode('utf-8') for i in range(0, len(message), MAX_PAYLOAD_SIZE)]
        total_fragments = len(fragments)
        
        print(f"[*] Mensagem será dividida em {total_fragments} fragmentos.")
        
        timeout_value = 2.0
        timer_start_time = 0
        
        # Loop principal de envio (FSM / Máquina de estados)
        while client_state["base"] < total_fragments:
            with lock:
                # 1. Enviar pacotes dentro da janela
                while client_state["next_seq_num"] < client_state["base"] + client_state["window_size"] and client_state["next_seq_num"] < total_fragments:
                    
                    seq = client_state["next_seq_num"]
                    data_pkt = Packet(
                        seq_num=seq,
                        flags=FLAG_DATA,
                        mode=mode,
                        payload=fragments[seq]
                    )
                    
                    # Simulação de erro (no cliente, antes de enviar)
                    if random.random() < args.drop:
                        print(f"[!] SIMULAÇÃO DE PERDA: Pacote {seq} dropado intencionalmente.")
                        # Não envia o pacote, simulando perda total na rede
                    elif random.random() < args.error:
                        print(f"[!] SIMULAÇÃO DE ERRO: Corrompendo pacote {seq}")
                        # Corrompe intencionalmente modificando a flag sem recalcular checksum
                        raw_bytes = bytearray(data_pkt.to_bytes())
                        raw_bytes[2] = 0xFF # Altera as flags, quebrando o checksum
                        sock.sendto(bytes(raw_bytes), server_addr)
                    else:
                        print(f"[*] Enviando fragmento {seq}: '{fragments[seq].decode()}'")
                        sock.sendto(data_pkt.to_bytes(), server_addr)
                    
                    if client_state["mode"] == MODE_GBN:
                        if client_state["base"] == client_state["next_seq_num"]:
                            timer_start_time = time.time()
                    elif client_state["mode"] == MODE_SR:
                        client_state["timers"][seq] = time.time()
                        
                    client_state["next_seq_num"] += 1
                
                # 2. Verificar timeouts
                current_time = time.time()
                if client_state["mode"] == MODE_GBN:
                    if timer_start_time > 0 and (current_time - timer_start_time) > timeout_value:
                        print(f"[TIMEOUT] GBN: Estourou timer para pacote base {client_state['base']}. Reenviando janela...")
                        timer_start_time = time.time()
                        # Reenvia todos da base ao next_seq_num
                        for i in range(client_state["base"], client_state["next_seq_num"]):
                            print(f"[*] Reenviando {i}")
                            pkt = Packet(seq_num=i, flags=FLAG_DATA, mode=mode, payload=fragments[i])
                            sock.sendto(pkt.to_bytes(), server_addr)
                            
                elif client_state["mode"] == MODE_SR:
                    for seq in range(client_state["base"], client_state["next_seq_num"]):
                        if seq not in client_state["acks"]:
                            if seq in client_state["timers"] and (current_time - client_state["timers"][seq]) > timeout_value:
                                print(f"[TIMEOUT] SR: Estourou timer para pacote {seq}. Reenviando...")
                                pkt = Packet(seq_num=seq, flags=FLAG_DATA, mode=mode, payload=fragments[seq])
                                sock.sendto(pkt.to_bytes(), server_addr)
                                client_state["timers"][seq] = time.time()
            time.sleep(0.05)
            
        print("[*] Todos os fragmentos confirmados!")
        
        # FASE 3: ENCERRAMENTO
        fin_pkt = Packet(seq_num=total_fragments, flags=FLAG_FIN, mode=mode)
        sock.sendto(fin_pkt.to_bytes(), server_addr)
        
        time.sleep(1) # Aguarda FIN ACK
        client_state["running"] = False
        
    except KeyboardInterrupt:
        client_state["running"] = False
        print("\nCliente encerrado.")
    finally:
        recv_thread.join()
        sock.close()

if __name__ == "__main__":
    main()
