import argparse
import socket
import time
import select
import sys
from utils import PacketHeader, compute_checksum

START = 0
DATA = 1
END = 2
ACK = 3

def create_packet(type: int, seq_num: int, data: bytes = b'') -> bytes:
    """Tạo một gói tin.

    Args:
        type (int): Loại gói tin
        seq_num (int): Số thứ tự của gói tin
        data (bytes, optional): Dữ liệu của gói tin. Mặc định là chuỗi rỗng (b'')

    Returns:
        bytes: Gói tin đóng gói dưới dạng byte
    """
    header = PacketHeader(type=type, seq_num=seq_num, length=len(data))
    checksum = compute_checksum(header / data)
    header.checksum = checksum
    return bytes(header / data)

def split_chunks(message: str, chunk_size: int = 1024):
    """Chia một message thành nhiều gói tin nhỏ và đóng gói thành các packet.

    Args:
        message (str): message
        chunk_size (int, optional): Kích thước tối đa mỗi chunk (bytes). Mặc định là 1024

    Returns:
        tuple[list[bytes], int]: 
            - Danh sách các gói tin đã được tạo
            - Tổng số gói tin đã tạo
    """
    # như trong repo nói là còn 1472 bytes cho cả packet_data và packet_header là 16 byte (4 trường int 4 byte) nên maximum cho 1 chunk of data là 1456
    chunks = [message[i:i+chunk_size].encode() for i in range(0, len(message), chunk_size)]
    chunks_length = len(chunks)
    data_packets = []
    # Bắt đầu từ 1 vì số thứ tự 0 là của gói START
    for i, chunk in enumerate(chunks):
        packet = create_packet(DATA, i + 1, chunk)
        data_packets.append(packet)
        
    return data_packets, chunks_length

def sender(receiver_ip: str, receiver_port: int, window_size: int):
    """Gửi messeages đến bên receiver.

    Args:
        receiver_ip (str): Địa chỉ IP của receiver
        receiver_port (int): Cổng receiver đang lắng nghe
        window_size (int): Số lượng gói tin tối đa trong một khung có thể gửi đi
    """
    
    # Tạo 1 socket mới với giao thức IPv4 và kiểu UDP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Đọc messages và split thành chunks
    message = sys.stdin.read()
    data_packets, chunks_length = split_chunks(message)
    
    # 1. Gửi gói START đầu tiên
    start_pkt = create_packet(START, 0)
    s.sendto(start_pkt, (receiver_ip, receiver_port))
    # Chờ nhận seq_num ACK của START là 1
    while True:
        # Chờ tối đa 0.5 giây xem socket s có dữ liệu đến hay không và gửi lại start_packet nếu socket rỗng
        readable, writable, exceptional = select.select([s], [], [], 0.5)
        if readable:
            pkt, address = s.recvfrom(2048)
            pkt_header = PacketHeader(pkt[:16])
            if pkt_header.type == ACK and pkt_header.seq_num == 1:
                break
        else:
            s.sendto(start_pkt, (receiver_ip, receiver_port))
    
    # Số thứ tự ACK tiếp theo mong đợi từ receiver
    base = 1  
    # Thứ tự của gói tin tiếp theo được gửi
    next_seq_num = 1  
    # seq_num -> packet
    window = {}  
    # Theo dõi những ack đã acknowledged (modified)
    acked = set()
    
    # 2. Gửi tất cả gói tin sau khi đã gửi gói START
    while base <= chunks_length:
        # Gửi các packets trong cửa sổ hiện tại
        while next_seq_num < base + window_size and next_seq_num <= chunks_length:
            # Do data_packet lưu gói 1 trở đi bắt đầu từ index 0
            pkt = data_packets[next_seq_num - 1]
            s.sendto(pkt, (receiver_ip, receiver_port))
            window[next_seq_num] = pkt
            next_seq_num += 1
        
        # a 500 milliseconds retransmission timer to automatically retransmit packets that were never acknowledged (one timer for all packets in the current window) )
        timeout = 0.5
        start_time = time.time()
        while time.time() - start_time < timeout:
            remaining_time = timeout - (time.time() - start_time)
            readable, writable, exceptional = select.select([s], [], [], remaining_time)
        
            if readable:
                pkt, address = s.recvfrom(2048)
                header = PacketHeader(pkt[:16])
                if header.type == ACK:
                    acked.add(header.seq_num)
                    
                    # Di chuyển vị trí đầu của cửa sổ tới smallest unacknowledged seq_num
                    while base in acked:
                        acked.remove(base)
                        window.pop(base, None)
                        base += 1
                    
                    # Nhận được hết gói tin
                    if base > chunks_length:
                        break
                    
        # Timeout: Chỉ gửi lại những gói chưa được acknowledge
        if time.time() - start_time >= timeout:
            end_of_window = min(base + window_size, chunks_length + 1)
            
            for seq in range(base, end_of_window):
                if seq not in acked and seq in window:
                    s.sendto(window[seq], (receiver_ip, receiver_port))
                    print(f"Timeout: Retransmitted packet {seq}")
    
    # 3. Gửi END packet
    end_seq_num = chunks_length + 1
    end_pkt = create_packet(END, end_seq_num)
    s.sendto(end_pkt, (receiver_ip, receiver_port))
    start_end_time = time.time()
    while True:
        remaining_time = 0.5 - (time.time() - start_end_time)
        # Sender exit sau khi qua 500 ms end_pkt được gửi
        if remaining_time <= 0:
            break
        
        # Sender nhận được ACK của end_pkt
        readable, writable, exceptional = select.select([s], [], [], remaining_time)
        if readable:
            pkt, address = s.recvfrom(2048)
            header = PacketHeader(pkt[:16])
            if header.type == ACK and header.seq_num > end_seq_num:
                break
    
    s.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "receiver_ip", help="The IP address of the host that receiver is running on"
    )
    parser.add_argument(
        "receiver_port", type=int, help="The port number on which receiver is listening"
    )
    parser.add_argument(
        "window_size", type=int, help="Maximum number of outstanding packets"
    )
    args = parser.parse_args()

    sender(args.receiver_ip, args.receiver_port, args.window_size)


if __name__ == "__main__":
    main()