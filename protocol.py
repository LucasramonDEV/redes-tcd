import struct

# Constantes do Protocolo
FLAG_SYN  = 1 << 0
FLAG_ACK  = 1 << 1
FLAG_NACK = 1 << 2
FLAG_FIN  = 1 << 3
FLAG_DATA = 1 << 4

MODE_GBN = 0
MODE_SR  = 1

# Tamanho do cabeçalho
HEADER_FORMAT = "!H H B B H H"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_SIZE = 4

# --- Ponto Extra 2: Criptografia Simétrica (RC4 feito à mão) ---
def rc4_crypt(data: bytes, key: bytes = b"redes_2026") -> bytes:
    """Implementação manual do algoritmo de criptografia simétrica RC4."""
    if not data:
        return b""
    
    # Key-scheduling algorithm (KSA)
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
        
    # Pseudo-random generation algorithm (PRGA)
    i = 0
    j = 0
    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        k = S[(S[i] + S[j]) % 256]
        out.append(byte ^ k)
        
    return bytes(out)

# --- Ponto Extra 1: Checksum feito à mão (Internet Checksum 16-bits) ---
def calculate_checksum(data: bytes) -> int:
    """Implementação manual de Checksum (soma de 16-bits em complemento de 1)."""
    if len(data) % 2 == 1:
        data += b'\0'
        
    checksum = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i+1]
        checksum += word
        checksum = (checksum & 0xffff) + (checksum >> 16)
        
    return (~checksum) & 0xffff

def verify_checksum(data: bytes, received_checksum: int) -> bool:
    """Verifica se o checksum calculado bate com o recebido."""
    return calculate_checksum(data) == received_checksum

# --- Classe para representar um pacote (Mensagem) ---
class Packet:
    def __init__(self, seq_num=0, ack_num=0, flags=0, mode=MODE_GBN, window_size=5, max_text_size=30, payload=b""):
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.flags = flags
        self.mode = mode
        self.window_size = window_size
        self.max_text_size = max_text_size
        self.payload = payload
        self.checksum = 0
        
    def to_bytes(self) -> bytes:
        # Criptografa o payload se for de dados
        encrypted_payload = rc4_crypt(self.payload) if self.payload else b""
        
        mode_window = (self.mode << 4) | (self.window_size & 0x0F)
        
        # Cria o cabeçalho com checksum 0 para o cálculo
        header = struct.pack(HEADER_FORMAT, self.seq_num, self.ack_num, self.flags, mode_window, self.max_text_size, 0)
        
        # Calcula o checksum sobre o pacote inteiro (header + payload encriptado)
        self.checksum = calculate_checksum(header + encrypted_payload)
        
        # Empacota novamente com o checksum correto
        header = struct.pack(HEADER_FORMAT, self.seq_num, self.ack_num, self.flags, mode_window, self.max_text_size, self.checksum)
        
        return header + encrypted_payload

    @classmethod
    def from_bytes(cls, data: bytes):
        if len(data) < HEADER_SIZE:
            raise ValueError("Pacote muito pequeno.")
            
        header = data[:HEADER_SIZE]
        encrypted_payload = data[HEADER_SIZE:]
        
        # Extrai os campos do cabeçalho
        seq_num, ack_num, flags, mode_window, max_text_size, received_checksum = struct.unpack(HEADER_FORMAT, header)
        
        # Verifica checksum
        header_for_calc = struct.pack(HEADER_FORMAT, seq_num, ack_num, flags, mode_window, max_text_size, 0)
        is_valid = verify_checksum(header_for_calc + encrypted_payload, received_checksum)
        
        mode = (mode_window >> 4) & 0x0F
        window_size = mode_window & 0x0F
        
        payload = rc4_crypt(encrypted_payload) if encrypted_payload else b""
        
        pkt = cls(seq_num, ack_num, flags, mode, window_size, max_text_size, payload)
        pkt.checksum = received_checksum
        pkt.is_corrupted = not is_valid
        
        return pkt

    def __str__(self):
        flags_str = []
        if self.flags & FLAG_SYN: flags_str.append("SYN")
        if self.flags & FLAG_ACK: flags_str.append("ACK")
        if self.flags & FLAG_NACK: flags_str.append("NACK")
        if self.flags & FLAG_FIN: flags_str.append("FIN")
        if self.flags & FLAG_DATA: flags_str.append("DATA")
        
        mode_str = "SR" if self.mode == MODE_SR else "GBN"
        
        return f"[Packet SEQ={self.seq_num} ACK={self.ack_num} FLAGS={'|'.join(flags_str)} MODE={mode_str} WIN={self.window_size} MAX_TEXT={self.max_text_size} CKSUM={'OK' if not getattr(self, 'is_corrupted', False) else 'FAIL'} PAYLOAD={self.payload}]"
