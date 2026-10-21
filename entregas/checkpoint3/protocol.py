import struct

# ── Flags do protocolo ──────────────────────────────────────────────────────
FLAG_SYN  = 1 << 0   # Inicia conexão
FLAG_ACK  = 1 << 1   # Confirmação positiva
FLAG_NACK = 1 << 2   # Confirmação negativa (SR: pede retransmissão imediata)
FLAG_FIN  = 1 << 3   # Encerramento
FLAG_DATA = 1 << 4   # Pacote de dados

# ── Modos de operação ────────────────────────────────────────────────────────
MODE_GBN = 0   # Go-Back-N
MODE_SR  = 1   # Selective Repeat

# ── Tamanho máximo de payload por fragmento ──────────────────────────────────
MAX_PAYLOAD_SIZE = 4   # <= 4 bytes por fragmento (exigência do enunciado)

# ── Formato do cabeçalho binário ─────────────────────────────────────────────
# ! = big-endian (rede)
# H = 2 bytes sem sinal  |  B = 1 byte sem sinal
# campos: seq_num(2) | ack_num(2) | flags(1) | mode(1) | window_size(2) | max_text_size(2) | checksum(2)
HEADER_FORMAT = "!H H B B H H H"
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)


# ────────────────────────────────────────────────────────────────────────────
# Ponto Extra 1 – Checksum 16-bits (Internet Checksum, complemento de 1)
# ────────────────────────────────────────────────────────────────────────────

def calculate_checksum(data: bytes) -> int:
    """Soma de 16 bits em complemento de 1 (mesmo algoritmo do IP/UDP/TCP)."""
    if len(data) % 2 == 1:
        data += b"\x00"       # padding se ímpar

    total = 0
    for i in range(0, len(data), 2):
        word   = (data[i] << 8) + data[i + 1]
        total += word
        total  = (total & 0xFFFF) + (total >> 16)   # carry around

    return (~total) & 0xFFFF


def verify_checksum(data: bytes, received: int) -> bool:
    return calculate_checksum(data) == received


# ────────────────────────────────────────────────────────────────────────────
# Ponto Extra 2 – Criptografia RC4 (implementação manual)
# ────────────────────────────────────────────────────────────────────────────

_RC4_KEY = b"redes_2026"

def rc4_crypt(data: bytes, key: bytes = _RC4_KEY) -> bytes:
    """Cifra/decifra com RC4 (simétrico: mesma função para ambos os sentidos)."""
    if not data:
        return b""

    # KSA – Key Scheduling Algorithm
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]

    # PRGA – Pseudo-Random Generation Algorithm
    i = j = 0
    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        k = S[(S[i] + S[j]) % 256]
        out.append(byte ^ k)

    return bytes(out)


# ────────────────────────────────────────────────────────────────────────────
# Classe Packet
# ────────────────────────────────────────────────────────────────────────────

class Packet:
    """Pacote completo do protocolo TCD – Checkpoint 3.

    Extras ativos:
        - Checksum 16-bits calculado sobre header + payload cifrado
        - Payload cifrado com RC4 antes de serializar
    """

    def __init__(self, seq_num=0, ack_num=0, flags=0,
                 mode=MODE_GBN, window_size=5, max_text_size=30, payload=b""):
        self.seq_num       = seq_num
        self.ack_num       = ack_num
        self.flags         = flags
        self.mode          = mode
        self.window_size   = window_size
        self.max_text_size = max_text_size
        self.payload       = payload
        self.is_corrupted  = False   # definido por from_bytes()

    # ── serialização ──────────────────────────────────────────────────────────
    def to_bytes(self) -> bytes:
        enc = rc4_crypt(self.payload) if self.payload else b""

        # Cabeçalho com checksum = 0 para o cálculo
        hdr = struct.pack(HEADER_FORMAT,
                          self.seq_num, self.ack_num, self.flags, self.mode,
                          self.window_size, self.max_text_size, 0)
        cksum = calculate_checksum(hdr + enc)

        # Cabeçalho final com checksum real
        hdr = struct.pack(HEADER_FORMAT,
                          self.seq_num, self.ack_num, self.flags, self.mode,
                          self.window_size, self.max_text_size, cksum)
        return hdr + enc

    # ── desserialização ───────────────────────────────────────────────────────
    @classmethod
    def from_bytes(cls, data: bytes) -> "Packet":
        if len(data) < HEADER_SIZE:
            raise ValueError("Pacote menor que o cabeçalho esperado.")

        hdr_raw = data[:HEADER_SIZE]
        enc     = data[HEADER_SIZE:]

        seq_num, ack_num, flags, mode, window_size, max_text_size, received_cksum = \
            struct.unpack(HEADER_FORMAT, hdr_raw)

        # Verifica checksum: recalcula com checksum=0 no campo
        hdr_zero = struct.pack(HEADER_FORMAT,
                               seq_num, ack_num, flags, mode,
                               window_size, max_text_size, 0)
        ok = verify_checksum(hdr_zero + enc, received_cksum)

        payload = rc4_crypt(enc) if enc else b""

        pkt = cls(seq_num, ack_num, flags, mode, window_size, max_text_size, payload)
        pkt.is_corrupted = not ok
        return pkt

    # ── representação legível ─────────────────────────────────────────────────
    def __str__(self) -> str:
        flags_str = []
        if self.flags & FLAG_SYN:  flags_str.append("SYN")
        if self.flags & FLAG_ACK:  flags_str.append("ACK")
        if self.flags & FLAG_NACK: flags_str.append("NACK")
        if self.flags & FLAG_FIN:  flags_str.append("FIN")
        if self.flags & FLAG_DATA: flags_str.append("DATA")
        mode_str  = "SR" if self.mode == MODE_SR else "GBN"
        cksum_str = "FAIL" if self.is_corrupted else "OK"
        return (
            f"[Packet SEQ={self.seq_num} ACK={self.ack_num} "
            f"FLAGS={'|'.join(flags_str) or 'NONE'} MODE={mode_str} "
            f"WIN={self.window_size} MAX_TEXT={self.max_text_size} "
            f"CKSUM={cksum_str} PAYLOAD={self.payload}]"
        )
