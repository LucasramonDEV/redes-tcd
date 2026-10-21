# Relatório – Checkpoint 1: Handshake & Sockets
## Trabalho I – Redes de Computadores

---

## O que foi entregue

Implementação da **fase de conexão inicial** entre cliente e servidor usando **sockets UDP** e um protocolo de handshake binário próprio.

O cliente envia um pacote **SYN** informando:
- O **modo de operação** desejado (Go-Back-N ou Selective Repeat)
- O **tamanho máximo do texto** que pretende enviar

O servidor responde com **SYN-ACK** confirmando:
- O modo de operação (ecoa o do cliente)
- O **tamanho da janela de recepção** (definido pelo servidor = 5)
- O **tamanho máximo do texto** aceito (definido pelo servidor = 30 bytes)

---

## O que estudar para responder ao monitor

### 1. Por que UDP e não TCP?

O trabalho exige implementar **a confiabilidade manualmente**. O TCP já faz isso automaticamente (ACK, retransmissão, controle de fluxo). Usar UDP nos obriga a construir cada mecanismo do zero, que é exatamente o objetivo do trabalho: entender como protocolos confiáveis funcionam por dentro.

### 2. O que é um socket UDP?

Um **socket** é o ponto de comunicação entre dois processos pela rede. No UDP:
- `socket.SOCK_DGRAM` cria um socket sem conexão
- Cada `sendto(dados, endereço)` manda um datagrama independente
- Cada `recvfrom(tamanho)` recebe um datagrama e diz de onde veio
- Não há garantia de entrega, ordem ou integridade — tudo isso precisa ser feito pelo protocolo

### 3. O que é um handshake?

É a **negociação inicial** antes de trocar dados. Serve para os dois lados concordarem com os parâmetros da comunicação antes de começar a enviar coisas de verdade.

No nosso protocolo:
```
Cliente                      Servidor
   |------ SYN (modo, max_text) ----->|
   |<----- SYN-ACK (modo, win, max) --|
   |         ESTABELECIDO             |
```

### 4. O que é o cabeçalho binário?

Em vez de mandar texto (como `"modo=GBN,janela=5"`), empacotamos os dados em bytes usando `struct.pack`. Isso é mais eficiente e realista — é como protocolos reais (IP, TCP, UDP) funcionam.

Nosso cabeçalho no CP1:
| Campo          | Tamanho | Descrição                        |
|----------------|---------|----------------------------------|
| `flags`        | 1 byte  | SYN (bit 0), ACK (bit 1)         |
| `mode`         | 1 byte  | 0 = GBN, 1 = SR                  |
| `window_size`  | 2 bytes | Janela de recepção do servidor    |
| `max_text_size`| 2 bytes | Limite máximo da mensagem         |

### 5. O que é modo de operação (GBN vs SR)?

São dois algoritmos de **envio em janela deslizante** para transmissão confiável:

- **Go-Back-N (GBN):** se um pacote der erro, o remetente reenvia aquele pacote **e todos os seguintes** (mesmo os que já chegaram certos). Simples de implementar, menos eficiente.

- **Selective Repeat (SR):** se um pacote der erro, o remetente reenvia **só aquele pacote**. O receptor guarda os que chegaram fora de ordem em buffer. Mais eficiente, mais complexo.

No CP1 apenas **negociamos qual modo usar** — a implementação real acontece no CP2 e CP3.

### 6. O que é tamanho da janela?

A **janela de recepção** (`window_size`) define quantos pacotes podem estar "em voo" ao mesmo tempo sem confirmação. No nosso protocolo, o **servidor define a janela = 5**, ou seja, o cliente pode enviar até 5 fragmentos antes de precisar esperar um ACK.

### 7. O que é max_text_size?

É o **limite máximo do buffer** — o maior tamanho que a mensagem do usuário pode ter. Definimos como 30 bytes. Se o usuário digitar mais, a mensagem é truncada. Esse valor é acordado no handshake para que cliente e servidor saibam o limite antes de começar a trocar dados.

---

## Como testar

Em dois terminais separados:

```bash
# Terminal 1 – inicia o servidor
python server.py --port 12000

# Terminal 2 – inicia o cliente (modo GBN)
python client.py --server 127.0.0.1 --port 12000 --mode gbn

# Terminal 2 – inicia o cliente (modo SR)
python client.py --server 127.0.0.1 --port 12000 --mode sr
```

**Saída esperada no servidor:**
```
[*] Servidor aguardando na porta 12000...
[RECEBIDO de ('127.0.0.1', XXXXX)] [Packet FLAGS=SYN MODE=GBN WIN=0 MAX_TEXT=30]
[*] Handshake iniciado pelo cliente.
    Modo solicitado    : GBN
[ENVIADO  para ('127.0.0.1', XXXXX)] [Packet FLAGS=SYN|ACK MODE=GBN WIN=5 MAX_TEXT=30]
[*] Handshake concluído com sucesso!
```

**Saída esperada no cliente:**
```
[*] Enviando SYN para ('127.0.0.1', 12000)...
[RECEBIDO] [Packet FLAGS=SYN|ACK MODE=GBN WIN=5 MAX_TEXT=30]
[*] Handshake concluído com sucesso!
    Modo confirmado    : GBN
    Janela definida    : 5
    Max texto aceito   : 30 bytes
```

---

## Resumo das escolhas de projeto

| Decisão               | Escolha                  | Motivo                                      |
|-----------------------|--------------------------|---------------------------------------------|
| Protocolo de rede     | UDP                      | Obrigatório pelo enunciado                   |
| Formato dos pacotes   | Binário com `struct`     | Eficiente e realista, como protocolos reais  |
| Quem define a janela  | Servidor                 | Simula controle de fluxo real                |
| Quem define max_text  | Servidor                 | Garante que cliente não exceda o buffer      |
| Flags                 | Bitmask (SYN=1, ACK=2)   | Padrão da área (igual ao TCP)                |
