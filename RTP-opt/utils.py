import binascii

from scapy.all import Packet, IntField


class PacketHeader(Packet):
    """Packetheader:
        4 int field and each is 4 bytes -> 16 bytes total

    Args:
        Packet (_type_): _description_
    """
    name = "PacketHeader"
    fields_desc = [
        IntField("type", 0),
        IntField("seq_num", 0),
        IntField("length", 0),
        IntField("checksum", 0),
    ]


def compute_checksum(pkt):
    return binascii.crc32(bytes(pkt)) & 0xFFFFFFFF