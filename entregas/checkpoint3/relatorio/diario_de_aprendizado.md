# Relatório – Checkpoint 3: Inserção de Erros e Perdas
## Trabalho I – Redes de Computadores

---

## O que foi entregue

Implementação **completa e final** do protocolo TCD, incluindo todos os checkpoints anteriores mais:

1. **Checksum 16-bits** (Internet Checksum) calculado manualmente — detecta corrupção
2. **Criptografia RC4** implementada manualmente — cifra o payload de cada fragmento
3. **Simulação de perda** — cliente e servidor podem dropar pacotes aleatoriamente
4. **Simulação de corrupção** — cliente pode corromper o payload (checksum vai falhar)
5. **Todos os comportamentos** de GBN e SR diante de erros são demonstrados

---

## Todos os cenários do protocolo demonstrados

| Cenário                        | GBN                                     | SR                                           |
|-------------------------------|------------------------------------------|----------------------------------------------|
| Canal sem erros                | Todos os fragmentos chegam em ordem; ACK cumulativo avança a janela | Igual ao GBN neste caso |
| Pacote de dados perdido       | Timeout → reenvia **toda a janela**      | Timeout → reenvia **só o fragmento perdido** |
| Pacote de dados corrompido    | Checksum falha → servidor **descarta** → timeout → reenvia toda a janela | Checksum falha → servidor envia **NACK** → cliente retransmite imediatamente |
| ACK perdido                   | Timeout → reenvia janela                 | Timeout → reenvia fragmento sem ACK          |
| ACK corrompido                | Checksum falha no cliente → ignorado → timeout | Igual ao GBN neste caso               |
| Fragmento duplicado           | Servidor descarta (seq < expected)       | Servidor confirma novamente mas não reprocessa |

---

## O que estudar para responder ao monitor

### 1. O que é o Checksum 16-bits e como funciona?

É um mecanismo de **detecção de erros** — não corrige, apenas detecta. O mesmo algoritmo usado pelo IP, UDP e TCP (Internet Checksum).

**Como funciona:**
1. Divide os dados em palavras de 16 bits
2. Soma todas as palavras em aritmética de complemento de 1
3. Inverte todos os bits (complemento de 1)
4. Resultado = campo checksum no cabeçalho

**Para verificar:** recalcula o checksum do pacote recebido (com o campo checksum zerado) e compara com o valor recebido. Se diferir → pacote corrompido.

```python
# Exemplo simplificado
dados = b"Hello"
checksum = calculate_checksum(dados)   # 0xB58E (exemplo)
# Na verificação: calculate_checksum(dados) == checksum → True (íntegro)
#                 se algum bit mudar → False (corrompido)
```

**Por que complemento de 1?** Porque o carry (vai-um) é adicionado de volta à soma, tornando a operação comutativa e fácil de implementar em hardware dos anos 70.

### 2. O que é RC4 e por que foi escolhido?

RC4 (Rivest Cipher 4) é uma **cifra de fluxo simétrica** — a mesma chave e a mesma função são usadas para cifrar e decifrar.

**Por que RC4?**
- Simples de implementar manualmente (2 loops: KSA + PRGA)
- Simétrico: cliente e servidor usam a mesma chave `"redes_2026"`
- Opera byte a byte com XOR — compatível com qualquer dado binário

**Como funciona:**
1. **KSA** (Key Scheduling): embaralha um vetor S[0..255] usando a chave → gera estado interno
2. **PRGA** (geração): produz um byte pseudo-aleatório para cada byte do dado → XOR com o dado

**Propriedade importante:** `rc4(rc4(dados)) == dados` — aplicar duas vezes retorna o original, então a mesma função serve para cifrar e decifrar.

**No protocolo:** o payload é cifrado antes de calcular o checksum e antes de enviar. O receptor decifra após verificar o checksum.

### 3. O que acontece quando um pacote é corrompido? (GBN vs SR)

**Go-Back-N:**
- Servidor detecta checksum inválido → **descarta silenciosamente** o pacote
- Nenhum ACK é enviado para aquele fragmento
- O timer do cliente estoura → cliente **reenvia toda a janela** (inclusive fragmentos que já chegaram certos)
- Ineficiente, mas simples

**Selective Repeat:**
- Servidor detecta checksum inválido → envia **NACK** com o número do fragmento corrompido
- Cliente recebe NACK → **retransmite imediatamente** só aquele fragmento (sem esperar timeout)
- Mais eficiente: não precisa esperar o timer; não reenvia fragmentos corretos

### 4. O que é perda de pacote vs corrupção de pacote?

- **Perda:** o pacote simplesmente não chega. O receptor não sabe que ele foi enviado. Detectado por **timeout** no remetente.
- **Corrupção:** o pacote chega, mas com bits alterados. Detectado por **checksum inválido** no receptor.

Na simulação:
- `--drop 0.3` = 30% de chance do pacote não ser enviado (simula perda na rede)
- `--error 0.3` = 30% de chance do pacote ser corrompido antes de sair (simula ruído)

### 5. Como a retransmissão por timeout funciona?

Cada vez que um pacote é enviado, o remetente inicia um **timer**:
- **GBN:** um único timer para o pacote mais antigo sem ACK (`base`)
  - Se estourar: reenvia `base` até `next_seq - 1`
- **SR:** um timer **por pacote** sem ACK
  - Se estourar: reenvia só aquele pacote

O timeout é configurado em 2 segundos. Se o ACK não chegar nesse tempo, assume-se perda ou corrupção e retransmite.

### 6. Por que o receptor SR guarda fragmentos fora de ordem em buffer?

Se o SR simplesmente descartasse fragmentos fora de ordem (como o GBN), o remetente precisaria reenviar todos eles quando o timeout estourasse — exatamente o comportamento do GBN. Para aproveitar a eficiência do SR, o receptor guarda os fragmentos que chegaram fora de ordem num **buffer** e só os entrega à aplicação quando o fragmento que faltava finalmente chegar e a sequência ficar completa.

---

## Como testar todos os cenários

```bash
# Terminal 1 – servidor com 20% de perda de ACK
python server.py --port 12000 --drop-ack 0.2

# Terminal 2 – GBN com 30% de perda de pacote
python client.py --mode gbn --drop 0.3

# Terminal 2 – SR com 30% de corrupção de pacote
python client.py --mode sr --error 0.3

# Cenário sem erros (igual ao CP2)
python client.py --mode gbn
```

**O que observar:**
- Com `--drop`: mensagens `[SIMULAÇÃO] Pacote SEQ=X PERDIDO` + depois `[TIMEOUT] GBN/SR ...`
- Com `--error`: mensagens `[SIMULAÇÃO] Pacote SEQ=X CORROMPIDO` + no servidor `[!] Pacote CORROMPIDO` + NACK (SR) ou descarte (GBN)
- Com `--drop-ack`: servidor dropa o ACK, cliente não recebe, timeout estoura, cliente retransmite
- Em todos os casos: a mensagem final exibida pelo servidor está **sempre correta e completa**

---

## Resumo das escolhas de projeto

| Decisão                        | Escolha                          | Motivo                                                     |
|-------------------------------|----------------------------------|------------------------------------------------------------|
| Checksum                      | Internet Checksum 16-bits manual | Mesmo algoritmo do IP/UDP/TCP; exigido como ponto extra    |
| Criptografia                  | RC4 manual                       | Simétrico, simples de implementar, exigido como ponto extra|
| Ordem: cifrar → checksum      | Checksum sobre dado cifrado      | Protege a integridade do dado já cifrado                   |
| NACK no GBN                   | Não usado                        | GBN classicamente não usa NACK; timeout é suficiente       |
| NACK no SR                    | Sim                              | Otimização: retransmissão imediata sem esperar timeout     |
| Simulação de erros            | No remetente (cliente)           | Mais controlável; simula ruído antes de sair na rede       |
| Simulação de perda de ACK     | No receptor (servidor)           | Simula perda no caminho de volta                           |
