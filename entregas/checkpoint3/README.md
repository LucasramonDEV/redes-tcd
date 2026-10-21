# TCD - Transporte Confiável de Dados (Camada de Aplicação)

Este projeto implementa um protocolo de Transporte Confiável de Dados (TCD) na camada de aplicação, rodando sobre UDP. O protocolo suporta controle de fluxo via janelamento e garante confiabilidade através do uso de números de sequência, reconhecimentos (ACK), temporizadores e checksum.

Suporta os modos **Go-Back-N (GBN)** e **Selective Repeat (SR)**.

## Arquitetura do Protocolo (Cabeçalho de 12 bytes)
- **Sequence Number (16 bits):** Número de sequência do pacote.
- **Ack Number (16 bits):** Número de reconhecimento.
- **Flags (8 bits):** Indicadores do tipo de pacote (SYN=1, ACK=2, NACK=4, FIN=8, DATA=16).
- **Mode & Window (8 bits):** Os 4 bits mais significativos indicam o modo (0=GBN, 1=SR) e os 4 menos significativos indicam o tamanho da janela (até 15).
- **Max Text Size (16 bits):** Limite de caracteres negociado no Handshake (mín. 30).
- **Checksum (16 bits):** Cálculo de integridade em complemento de 1 (Internet Checksum) feito sobre o cabeçalho e payload.

> **Payload:** A carga útil para pacotes de DATA tem no máximo 4 bytes, criptografada usando algoritmo simétrico RC4.

## Execução Básica (Checkpoint 1 e 2)

**1. Iniciar o servidor:**
```bash
python server.py --port 12000
```

**2. Iniciar o cliente:**
```bash
# Modo Go-Back-N (padrão)
python client.py --server 127.0.0.1 --port 12000 --mode gbn

# Modo Selective Repeat
python client.py --server 127.0.0.1 --port 12000 --mode sr
```

## Simulação de Erros e Perdas (Checkpoint 3)
O cliente pode ser configurado para simular o envio de pacotes corrompidos (checksum inválido) ou perdas severas de pacotes, forçando o servidor a descartá-los (ou enviar NACK) e exigindo a retransmissão por estouro de temporizador (timeout) na origem.

```bash
# Simula uma taxa de corrupção de 30% no envio de pacotes
python client.py --mode gbn --error 0.3

# Simula uma taxa de perda (drop total) de 20%
python client.py --mode sr --drop 0.2
```
