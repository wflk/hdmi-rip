#! /usr/bin/env python

# HDMI to IP network extender ripper

# Adam Laurie <adam@algroup.co.uk> - 2016
# 
#  https://github.com/AdamLaurie/hdmi-mjpeg
#
# 1st cut: 15th July 2016
#
# code based on original:
#
#Packet sniffer in python
#For Linux - Sniffs all incoming and outgoing packets :)
#Silver Moon (m00n.silv3r@gmail.com)
#modified by danman


import signal
import socket, sys, os
from struct import *
import struct
import binascii
import time, datetime
from optparse import OptionParser
import wave


MESSAGE = "5446367A600200000000000303010026000000000234C2".decode('hex')
AUDIO_HEADER= "00555555555555555555555500000000".decode('hex')
exitvalue= os.EX_OK


usage= "usage: %prog [options] <file prefix> [minutes]"
parser= OptionParser(usage= usage)
parser.add_option("-a", "--audio_rate", type="int", dest="audio_rate", default= 48000, help="audio data rate in Hz (48000)")
parser.add_option("-c", "--audio_channels", type="int", dest="audio_channels", default= 2, help="audio channels (2)")
parser.add_option("-l", "--local_ip", dest="local_ip", default= "0.0.0.0", help="use local IP address as source (0.0.0.0)")
parser.add_option("-p", "--sender_port", type="int", dest="sender_port", default= 48689, help="set sender's UDP PORT (48689)")
parser.add_option("-q", "--quiet", action="store_false", dest="verbose", default= True, help="don't print status messages to stdout (False)")
parser.add_option("-s", "--sender_ip", dest="sender_ip", default= "192.168.168.55", help="set sender's IP address (192.168.168.55)")
parser.add_option("-S", "--strict", action="store_true", dest="strict", default= False, help="strict mode - abort recording if frames dropped")
parser.add_option("-w", "--wave", action="store_true", dest="wave", default= False, help="save audio in .wav format")
(options, args) = parser.parse_args()

if not (len(args) == 1 or len(args) == 2):
	parser.print_help()
	exit(0)

def log(message):
	if not options.verbose:
		return
	print message

def signal_handler(signal, frame):
	log('\nFlushing buffers...')
	if not options.wave:
		Audio.flush()
		os.fsync(Audio.fileno())
	Audio.close()
	log('Audio: %d frames, %d bytes (%d frames dropped)' % (Audio_Frames, Audio_Bytes, Audio_Dropped))
	Video.flush()
	os.fsync(Video.fileno())
	Video.close()
	log('Video: %d frames, %d bytes (%d frames dropped)' % (Video_Frames, Video_Bytes, Video_Dropped))
	sys.exit(exitvalue)

def keepalive():
	Keepalive_sock.sendto(MESSAGE, (options.sender_ip, options.sender_port))

#Convert a string of 6 characters of ethernet address into a dash separated hex string
def eth_addr (a) :
  b = "%.2x:%.2x:%.2x:%.2x:%.2x:%.2x" % (ord(a[0]) , ord(a[1]) , ord(a[2]), ord(a[3]), ord(a[4]) , ord(a[5]))
  return b

log("UDP target IP: %s" % options.sender_ip)
log("UDP keepalive port: %d" % options.sender_port)

try:
	record_time= int(args[1])
	log('Recording will cease after %d minutes' % record_time)
except:
	record_time= None
end_time= None
if options.strict:
	log('Recording will be aborted if any frame is dropped')


Keepalive_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP socket for keepalives
Keepalive_sock.bind((options.local_ip, options.sender_port)) # send from the correct port or it will be ignored

# detect quit
signal.signal(signal.SIGINT, signal_handler)

try:
    s = socket.socket( socket.AF_PACKET , socket.SOCK_RAW , socket.ntohs(0x0003))
except socket.error , msg:
    print 'Socket could not be created. Error Code : ' + str(msg[0]) + ' Message ' + msg[1]
    sys.exit()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
mreq = struct.pack("=4sl", socket.inet_aton("226.2.2.2"), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

sender="000b78006001".decode("hex")
Videostarted=0

if options.wave:
	Audio=wave.open(args[0] + "-audio.wav","w")
	Audio.setnchannels(options.audio_channels)
	Audio.setsampwidth(4)
	Audio.setframerate(options.audio_rate)
	log('Audio: %s-audio.wav' % args[0])
else:
	Audio= open(args[0] + "-audio.dat","w")
	log('Audio: %s-audio.dat' % args[0])
Video= open(args[0] + "-video.dat","w")
log('Video: %s-video.dat' % args[0])
Video_Frames= 0
Video_Bytes= 0
Video_Dropped= 0
Audio_Frames= 0
Audio_Bytes= 0
Audio_Dropped= 0

# keep track of dropped frames
frame_prev= None
part_prev= 0

packet_started= False
senderstarted= False
outbuf= ''
dropping= False

# receive a packet
while True:
    packet = s.recvfrom(65565)

    if not packet_started:
	log('Listener active at %s' % datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
	packet_started= True

    #packet string from tuple
    packet = packet[0]

    #parse ethernet header
    eth_length = 14

    eth_header = packet[:eth_length]
    eth = unpack('!6s6sH' , eth_header)
    eth_protocol = socket.ntohs(eth[2])

    if (packet[6:12] == sender) & (eth_protocol == 8) :

        #Parse IP header
        #take first 20 characters for the ip header
        ip_header = packet[eth_length:20+eth_length]

        #now unpack them :)
        iph = unpack('!BBHHHBBH4s4s' , ip_header)

        version_ihl = iph[0]
        version = version_ihl >> 4
        ihl = version_ihl & 0xF

        iph_length = ihl * 4

        ttl = iph[5]
        protocol = iph[6]
        s_addr = socket.inet_ntoa(iph[8]);
        d_addr = socket.inet_ntoa(iph[9]);

        #UDP packets
        if protocol == 17 :
		u = iph_length + eth_length
		udph_length = 8
		udp_header = packet[u:u+8]

		#now unpack them :)
		udph = unpack('!HHHH' , udp_header)

		source_port = udph[0]
		dest_port = udph[1]
		length = udph[2]
		checksum = udph[3]

		#get data from the packet
		h_size = eth_length + iph_length + udph_length
		data = packet[h_size:]

		# audio
		if (dest_port==2066) and Videostarted:
			if data[:16] == AUDIO_HEADER:
				if options.wave:
					data= data[16:]
					# write as little-endian
					Audio.writeframesraw(''.join([data[i:i+4][::-1] for i in range(0, len(data), 4)]))
				else:
					Audio.write(data[16:])
				Audio_Bytes += len(data[16:])
				Audio_Frames += 1
			else:
				log('Audio frame dropped')
				Audio_Dropped += 1
				if options.strict:
					log('Aborting due to audio frame drop!')
					exitvalue= os.EX_DATAERR
					os.kill(os.getpid(), signal.SIGINT)

		if (dest_port==2068):
			if not senderstarted:
				log('Sender active at %s' % datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
				senderstarted= True
			frame_n=ord(data[0])*256+ord(data[1])
			# data[2] is not part of the frame number - if it is set to 0x80 that means this is the last frame
			#part=ord(data[2])*256+ord(data[3])
			part=ord(data[3])
			if (part == 0):
				if not Videostarted:
					start_time= time.time()
					log("Video stream started at frame %s %s" % (frame_n, datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')))
					log('CTL-C to exit')
					Videostarted= 1
					if record_time:
						end_time= record_time * 60 + start_time
						log('Recording will stop automatically at: %s' % datetime.datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S'))
				frame_prev= frame_n
				Video.write(outbuf)
				Video_Bytes += len(outbuf)
				Video_Frames += 1
				outbuf= ''
				if dropping:
					Video_Dropped += 1
					if options.strict:
						log('Aborting due to video frame drop!')
						exitvalue= os.EX_DATAERR
						os.kill(os.getpid(), signal.SIGINT)
				dropping= False
				if end_time and time.time() >= end_time:
					log("Time's up!")
					os.kill(os.getpid(), signal.SIGINT)
			elif Videostarted:
				if not frame_prev == frame_n:
					log('Video dropped frame % d' % frame_n)
					frame_prev= frame_n
					outbuf= ''
					dropping= True
				if not part_prev + 1 == part:
					log('Video dropped part %d of frame %d' % (part, frame_n))
					outbuf= ''
					dropping= True
			if Videostarted and not dropping:
				outbuf += data[4:]
			part_prev= part
    		keepalive()

