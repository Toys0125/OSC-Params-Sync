#!/bin/env python3
# Original Script by JayJay, provided by Fuuujin
# Scripted Edited and Improved by Toys0125
from pythonosc import udp_client
from pythonosc import dispatcher
from pythonosc import osc_server
import threading
import sys
import csv
import time
import os
import logging
import json


config = {}
if(not os.path.exists('config.json')):
	config['serverPort']=9001
	config['serverIp']='127.0.0.1'
	config['clientPort']=9000
	config['clientIp']='127.0.0.1'
	config['packetDelay']=0.2
	config['debugMode']=False
	with open('config.json','a+') as outfile:
		json.dump(config,outfile,indent=2)
else:
	config = json.load(open('config.json','r'))
if(config['debugMode']):
	logging.basicConfig(level=logging.DEBUG)
else:
	logging.basicConfig(level=logging.INFO)

OSC_FloatId = 0
OSC_FloatValue = 0.0
sleep_delay = config['packetDelay']
numFloats = 0
serverThread = None
avatarid="Empty"
rows = [0.0]
globalLock = threading.Lock()
changingValue = False

def start_server(ip=config['serverIp'], port=config['serverPort']):
	global serverThread
	#This defines the server for receiving OSC messages
	logging.info(f"Listening on {ip}:{port}")
	server = osc_server.ThreadingOSCUDPServer((ip, port), dispatcher)
	serverThread = threading.Thread(target=server.serve_forever)
	serverThread.daemon = True
	serverThread.start()

def send_message(address, value, ip=config['clientIp'], port=config['clientPort']):
	#This defines sending OSC messages
	logging.debug(f"Send {address} : {value}")
	client = udp_client.SimpleUDPClient(ip, port)
	thread = threading.Thread(target=client.send_message, args=(address, value))
	thread.start()

def handle_float_id(address, *args):
	global OSC_FloatId, OSC_FloatValue, numFloats, globalLock, rows, changingValue #Added numFloats

	logging.debug(f"Start handle_float_id")

	# float id resets to 0 when a radial puppet menu was just closed. 
	if args[1] == 0:
		# Now we can save the last value to our csv.
		logging.info(f"handle_float_id given args[1]: {args[1]}")
		write_float(OSC_FloatId, OSC_FloatValue)
		changingValue = False
		return

	# float id is non-zero, thus a radial puppet is currently open. Save float id for later and wait.
	OSC_FloatId = args[1]
	numFloats = max(numFloats, OSC_FloatId) #added
	logging.info(f"remembering float id: {args[1]}")
	with globalLock:
		if len(rows) < OSC_FloatId:
			logging.info(f"More parameters than expected")
			logging.debug('Difference is %s',(OSC_FloatId - len(rows)))
			rows.extend([[0.0]] * (OSC_FloatId - len(rows)))  # Add empty rows if necessary
			logging.debug(f"{len(rows)} rows and data of %s",rows)

def handle_float_value(address, *args):
	global OSC_FloatValue, OSC_FloatId, changingValue
	OSC_FloatValue = args[1]
	changingValue = True
	logging.debug(f"remembering float value: {args[1]}")
	thread = threading.Thread(target=changeDataRows) # Insurance that there will be atleast a thread after each change.
	thread.start()
	

def changeDataRows():
	global OSC_FloatValue, OSC_FloatId, globalLock, rows
	with globalLock:
		if len(rows) < OSC_FloatId:
			logging.info(f"More parameters than expected")
			rows.extend([[0.0]] * (OSC_FloatId - len(rows)))  # Add empty rows if necessary
			logging.debug('Calculations is %s',(OSC_FloatId - len(rows)))
			logging.debug(f"{len(rows)} rows and data of %s",rows)

		rows[OSC_FloatId-1] = [OSC_FloatValue]
		send_message("/avatar/parameters/OPS_Id",OSC_FloatId)

def handle_avatar_change(address, *args):
	global avatarid, globalLock
	avatarid=args[1]
	logging.info(f"Avatar id is:{args[1]}")
	with globalLock:
		initialize_csv()



def write_float(floatId, floatValue):
	global avatarid,globalLock
	logging.info(f"write_float given {floatId} {floatValue}")
	
	
	with globalLock:
		with open(f'{avatarid}.csv', 'r') as csvfile:
			reader = csv.reader(csvfile)
			rows = list(reader)
			
			if len(rows) >= floatId:
				rows[floatId-1] = [floatValue]
			else:
				logging.info(f"Writing more parameters")
				rows.extend([[0]] * (floatId - len(rows) -1))  # Add empty rows if necessary
				rows.append([floatValue])
					
	with open(f'{avatarid}.csv', 'w', newline='') as csvfile:
		writer = csv.writer(csvfile)
		writer.writerows(rows)

def initialize_csv():
	global numFloats, avatarid, rows
	if(not os.path.exists(f'{avatarid}.csv')):
		with open(f'{avatarid}.csv','x', newline='') as csvfile:
			writer = csv.writer(csvfile)
			writer.writerow('')

	with open(f'{avatarid}.csv', 'r') as csvfile:
		reader = csv.reader(csvfile)
		rows = list(reader)

		# check if csv has too many rows, if so, clear csv
		if len(rows) > numFloats:
			numFloats = len(rows)
                        
		if len(rows) > numFloats:
			rows = []

		defaultValue = 0

		# for each float value we need to store
		for i in range(numFloats):
			# check if row already exists
			if i < len(rows):
				# check if zeroed data exists at that row
				if len(rows[i]) == 0:
					rows[i] = [defaultValue]
			else:
				rows.append([defaultValue])

	with open(f'{avatarid}.csv', 'w', newline='') as csvfile:
		writer = csv.writer(csvfile)
		writer.writerows(rows)

count = 0
def send_floats():
	global count, globalLock, rows, changingValue
	#This part of the module sends the stored values in memory.
	#3 Example values are being send here.
	if(changingValue):
		#send_message("/avatar/parameters/OPS_Id", 0)
		time.sleep(0.5)
		return
	if (count > 10): #Doing this to reduce logging as I have issues with it using to much ram in the windows terminal.
		logging.info(f"{len(rows)} Rows, Local Floats are %s", rows)
		count = 0
	count+=1
	with globalLock:
		for i, row in enumerate(rows):
			if(changingValue):
				break
			value = float(row[0])

			send_message("/avatar/parameters/OPS_Id", i + 1)
			send_message("/avatar/parameters/OPS_Float", value)
			time.sleep(sleep_delay)

def main():
	# Maps an address to the dispatcher and receives a callback function.
	dispatcher.map("/avatar/parameters/OPS_ReceiveId", handle_float_id, "OSC_OUT_FloatId")
	dispatcher.map("/avatar/parameters/OPS_ReceiveFloat", handle_float_value, "OSC_OUT_FloatValue")
	dispatcher.map("/avatar/change", handle_avatar_change, "OSC_AVATAR_ID")
#	initialize_csv()
	start_server()

def main_send():
	global avatarid
	if (avatarid=="Empty"):
		logging.info("Waiting on avatar change")
		time.sleep(1)
		return
	send_floats()

if __name__ == "__main__":
	dispatcher = dispatcher.Dispatcher()
	main()
	logging.debug(sys.version)
	while serverThread.is_alive():
		main_send()
	
	# holds the program alive while the thread is running in the background.
	input("Press Enter to quit... \n")
	print("Quitting...")
