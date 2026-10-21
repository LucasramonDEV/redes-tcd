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

## Handshake de 3 vias (SYN → SYN-ACK → ACK)
1. **Cliente → SYN** (`seq = ISN_c`, modo e max_text propostos). Cliente vai para `SYN_SENT`.
2. **Servidor → SYN-ACK** (`seq = ISN_s`, `ack = ISN_c + 1`, janela = 5). Servidor vai para `SYN_RCVD` (**ainda não** conectado).
3. **Cliente → ACK** (`seq = ISN_c + 1`, `ack = ISN_s + 1`). Cliente vai para `ESTABLISHED`; o servidor só vai para `ESTABLISHED` ao receber e validar este ACK.

Confiabilidade do handshake sobre UDP:
- SYN ou SYN-ACK perdido: o cliente reenvia o SYN (4 tentativas, 1 s cada).
- ACK final perdido: o servidor reenvia o SYN-ACK por timer (1 s, até 5 vezes, depois descarta a conexão semiaberta); o cliente responde a SYN-ACK duplicado reenviando o ACK.
- DATA recebido em `SYN_RCVD` é descartado e provoca reenvio do SYN-ACK; o dado é recuperado pela retransmissão normal.

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
