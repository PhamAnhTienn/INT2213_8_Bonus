import argparse
import socket
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

def receiver(receiver_ip: str, receiver_port: int, window_size: int):
    """Nhận gói tin từ sender

    Args:
        receiver_ip (str): Địa chỉ IP của receiver
        receiver_port (int): Cổng receiver đang lắng nghe
        window_size (int): Số lượng gói tin tối đa trong một khung có thể gửi đi
    """
    
    # Tạo 1 socket mới với giao thức IPv4 và kiểu UDP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Gán địa chỉ IP và port vào socket để nhận dữ liệu đến cổng đó
    s.bind((receiver_ip, receiver_port))
    
    # Biến boolean để handle 1 sender at a time
    in_connection = False
    # Bộ đệm lưu các gói tin nhận sai thứ tự
    buffer = {}
    # Số thứ tự của gói tin mong đợi tiếp theo
    expected_seq_num = 1
    
    with open('RTP-opt/output.txt', 'wb') as f:
        while True:
            pkt, address = s.recvfrom(2048)
            header = PacketHeader(pkt[:16])
            
            # Logging xem nhận được gói tin chưa
            print(f"Received packet: type={header.type}, seq_num={header.seq_num}")
            sys.stdout.flush()
            
            if not in_connection:
                # 1. Nhận được START pkt và thiết lập kết nối và gửi lại ACK cho gói START
                if header.type == START and header.seq_num == 0:
                    in_connection = True
                    expected_seq_num = 1
                    ack_pkt = create_packet(ACK, 1)
                    print("Connection established, sending ACK for START")
                    s.sendto(ack_pkt, address)
            else:
                # 2. Nhận được data pkt
                if header.type == DATA:
                    # Tính checksum bên receiver xem có match với bên sender gửi hay không
                    received_checksum = header.checksum
                    header.checksum = 0
                    computed_checksum = compute_checksum(header / pkt[16:])
                    
                    # Checksum bên receiver match với bên sender 
                    if received_checksum == computed_checksum:
                        seq_num = header.seq_num
                        
                        # Gửi lại gói tin ack độc lập cho từng pkt trong window
                        if seq_num >= expected_seq_num and seq_num < expected_seq_num + window_size:
                            ack_pkt = create_packet(ACK, seq_num)
                            s.sendto(ack_pkt, address)
                        
                            # If it expects a packet of sequence number N and If it receives a packet with seq_num=N
                            if seq_num == expected_seq_num:
                                data = pkt[16:16 + header.length]
                                f.write(data)
                                expected_seq_num += 1
                            
                                # check for the highest sequence number (say M) of the in­order packets it has already received
                                while expected_seq_num in buffer:
                                    f.write(buffer[expected_seq_num])
                                    del buffer[expected_seq_num]
                                    expected_seq_num += 1
                                    
                                print(f"Packet {seq_num} received in order, ACK sent")
                                sys.stdout.flush()
                                
                            # If it expects a packet of sequence number N and If it receives a packet with seq_num not equal to N
                            else:
                                if seq_num not in buffer:
                                    buffer[seq_num] = pkt[16:16 + header.length]
                                    print(f"Buffered out-of-order packet {seq_num}, ACK sent")
                        # Bỏ pkt ngoài window
                        else:
                            print(f"Dropped packet {seq_num} outside window")  
                
                            
                # 3. Nhận được end_pkt
                elif header.type == END and header.seq_num == expected_seq_num:
                    ack_pkt = create_packet(ACK, expected_seq_num + 1)
                    s.sendto(ack_pkt, address)
                    
                    print(f"Received END packet")
                    sys.stdout.flush()
                    
                    break

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

    receiver(args.receiver_ip, args.receiver_port, args.window_size)


if __name__ == "__main__":
    main()