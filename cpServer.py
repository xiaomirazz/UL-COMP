#!/usr/bin/env python

import cherrypy, random, threading, time, socket, subprocess, atexit, os, datetime, sys, struct,thread
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket

# web server socket: 8000
# WebSocket socket: 8000 
# UDP socket for MacroCell Testbed (MCTB): 9000
cherrypy.config.update({'server.socket_port': 8000})
WebSocketPlugin(cherrypy.engine).subscribe()
cherrypy.tools.websocket = WebSocketTool()

SUBSCRIBERS = set()
HANDSHAKE_MESSAGE = 'STARTTEST'
ON = 'ON'
OFF = 'OFF'
UDP_IP = "172.16.124.133"
UDP_PORT = 8808
connections = []
CurCell = 0

# Semaphore
BUFLEN = 65565
semaphore_full_buffer = threading.Semaphore(0)
semaphore_empty_buffer = threading.Semaphore(BUFLEN)
messageQ = []

    # Create log file for each test case and save logs of different types
class LogFile:
    def __init__(self):
        self.tscnt = 0
        self.cflag = True
        self.dir = './Logs'
        if not os.path.exists(self.dir):
            os.mkdir(self.dir)
        self.open('Start')

    # create new log file if test cast stop message was received earlier
    def open(self,msg):
        if self.cflag == True:
            self.cflag = False
            t = datetime.datetime.now()
            f = '/{0}{1:02d}{2:02d}-{3:02d}{4:02d}{5:02d}_DRXSystemTest_TS{6:02d}.log'.format(t.year,t.month,t.day,t.hour,t.minute,t.second,self.tscnt)
            self.tscnt += 1
        try: self.fh.close()
        except: pass
        self.fh = file(self.dir+f,'w')

    # write log message to file
    def write(self,msg,logtype='INTERNAL',fidx=1):
        t = datetime.datetime.now()
        m = '{0:2d}:{1:2d}:{2:02d}.{3:06d} [{4}] {5}: {6}\n'.format(t.hour,t.minute,t.second, t.microsecond,sys._getframe(fidx).f_code.co_name,logtype,msg)
        self.fh.write(m)

    # write STATISTICS to file (TBD)
    def statistics(self,msg):
        self.write(msg,'STATISTICS',2)

    # restart new test scenario file
    def close(self,msg):
        self.cflag = True
        self.fh.flush()

    def __del__(self):
        try: self.fh.close()
        except: pass

#global instance for logging
log = None
#class Cmd(threading.Thread):
#    def run(self):
 #       print 'start cmd'
#	sock = socket.socket(socket.AF_INET,
#				socket.SOCK_STREAM)
#	sock.bind()
class RecvDRXNotification(threading.Thread):
    global log
       
    def run (self):
	global CurCell
        print 'Start DRX test'
        sock = socket.socket(socket.AF_INET, # Internet
                             socket.SOCK_DGRAM) # UDP
        sock.bind((UDP_IP, UDP_PORT))
        print 'bound to ', UDP_PORT     
       
       # ifndef USED_BY_UE
       # CellID = message[150:154]  
       # SectorID = message[154:158]
       # ULMCS = message[142:146]
       # DLMCS = message[146:150]
       # ULSNR = message[170:174];
       # AverPer = message[226:230];
       # ULTotalBits = message[234:242]; 
       # DLTotalBits = message[242:250];
       # ULThroughput = message[250:254];
       # DLThroughput = message[254:258];
	
        while True:
	    print 'waiting'  
            message, addr = sock.recvfrom(65565) # buffer size is 1024 bytes
            print'in recv loop'
            result = ''
            CellID = struct.unpack('<i',message[6966:6970])
            SectorID = struct.unpack('<i',message[6970:6974])
	    ULMCS = struct.unpack('<i',message[6958:6962])
	    DLMCS = struct.unpack('<i',message[6962:6966])
	    ULSNR = struct.unpack('<f',message[6986:6990])
	    ULThroughput = struct.unpack('<i',message[7066:7070])
	    DLThroughput = struct.unpack('<i',message[7070:7074])
	    if CurCell == CellID[0]:	
		result = str(CellID[0])+','+str(SectorID[0])+','+str(ULMCS[0])+','+str(DLMCS[0])+','+str(ULSNR[0])+','+str(ULThroughput[0])+','+str(DLThroughput[0])
	   	print 'Cell ',CurCell,': ',result
           	semaphore_empty_buffer.acquire()
           	[messageQ.append(result)]  
           	semaphore_full_buffer.release()
		
        sock.close()

class Publisher(WebSocket):
    def __init__(self, *args, **kw):
        print 'Publisher().__init__...'
        WebSocket.__init__(self, *args, **kw)
        SUBSCRIBERS.add(self)

    def sending(self):
	while True:
	    print 'sending!'
	    semaphore_full_buffer.acquire()
            message = messageQ.pop(0)               
            semaphore_empty_buffer.release()
            self.send(message,False) 

    def test_start(self):
        print 'test start'
        global log
        log = LogFile()
        threadDRX=RecvDRXNotification() 
        threadDRX.daemon = True  # needed to kill thread with Ctrl-C
        threadDRX.start()
        thread.start_new_thread(self.sending,())

    def cmd(self,msg):
	global CurCell
	sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
	if msg == OFF:
	    data = struct.pack('!hbbhd',0x01,1,0x21,8,0)
	    sock.sendto(data,('172.16.124.69',8810))
	    print 'send 0 to cmdAgent'
	elif msg == ON:
	    data = struct.pack('!hbbhBBBBBBBB',0x01,1,0x21,8,0,0,0,0,0,0,0xf0,0x3f)
	    sock.sendto(data,('172.16.124.69',8810))
	    print 'send 1 to cmdAgent'
	else:
	    CurCell = int(msg)
	sock.close()

    def received_message(self,message):
        print 'Publisher().received: ', message
        if message.data == HANDSHAKE_MESSAGE: 
            self.test_start() 
	else:
	    self.cmd(message.data) 

    def closed(self, code, reason=None):
        print 'Publisher().closed...'
        SUBSCRIBERS.remove(self)

class Root(object):
    @cherrypy.expose
    def index(self):
        print 'Root().index()...'
        return open('ws_browser.html').read()

    @cherrypy.expose
    def ws(self):
        print 'Root().ws...'  #"Method must exist to serve as a exposed hook for the websocket"

    @cherrypy.expose
    def notify(self, msg):
        for conn in SUBSCRIBERS:
            conn.send(msg)

   # def cleanup():
        #devnull = open('/dev/null', 'w')
        #process = subprocess.Popen(['killall','-9','iperf'], stdout=devnull, stderr=devnull)
    
   #atexit.register(cleanup)


cherrypy.quickstart(Root(), '/', config={'/ws': {'tools.websocket.on': True,
                                                 'tools.websocket.handler_cls': Publisher}})





		
		
		
