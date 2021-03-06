#!/usr/bin/env python3

# Polls the Theorem Prover Competition Webserver for new Lean submissions

import subprocess
import requests
import json
import sys
import time
import re
import logging

install_path = "/home/hoelzl/Projects/competition/"

pollurl = "pollsubmission/?itp=LEA"
puturl = "putresult/"
path = install_path

lean_bin = install_path + "lean-3.4.1-linux/bin/"
compile_command = [lean_bin + "lean", "check.lean", "-E", "check.out", "--only-export=main_theorem"]
check_command = [lean_bin + "leanchecker", "check.out", "main_theorem"]

axiom_re = re.compile("axiom ([^ ]*) .*")

if __name__ == "__main__":
	loglevel = logging.INFO

	if len(sys.argv) > 1:
		if sys.argv[1] == "DEBUG":
			loglevel = logging.DEBUG

	## INITIALIZE LOGGING
	logging.basicConfig(
#		filename = "poller.log",
		stream   = sys.stderr,
		filemode = 'a',
		format   = '%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
		datefmt  = '%m-%d %H:%M:%S',
		level    = loglevel)

	logger = logging.getLogger('poller')

	logger.info("## Lean Poller")
	logger.debug("In debug mode")

	logger.info("Reading config")
	config_file = open("config", "r")
	config = json.loads(config_file.read())
	config_file.close()

	token = config["token"]
	baseurl = config["baseurl"]
	headers = {
		"Content-Type": "application/json",
		"Authorization": "Token %s" % token
	}

	logger.info("Token: %s" % token)

	logger.info("Starting the polling loop")
	while True:
		## poll from server
		logger.debug("Poll from server")

		url = baseurl + pollurl

		# send get request
		my_response = requests.get(url, verify = True, headers = headers)
		logger.debug ("Sent GET request to " + url)

		# work with answer
		if(my_response.ok):
			jData = json.loads(my_response.content)

			# NO TASK available
			if jData["sID"] == -1:
				logger.debug( "no submission found - sleep some time")
				time.sleep(5)

			# Got a task to grade:
			else:
				logger.info("==================================================")
				logger.info("got submission " + str(jData["sID"]) + " to grade.")

				logger.debug("The grading-task data contains {0} properties".format(len(jData)))
				logger.debug("\n")
				for key in jData:
					logger.debug( key + " : " + str(jData[key]))

				submissionId=jData["sID"]
				assessmentId=jData["aID"]
				allow_sorry=jData["allow_sorry"]

				#### STARTING FROM HERE things get ProofAssistant-specific
				# all the necessary data is here:
				#  the submission ID:		submissionId
				#  the assessment ID:		assessmentId
				#  the defs file:			jData["files"]["Defs"]
				#  the submission file:		jData["files"]["Submission"]
				#  the check file:			jData["files"]["Check"]
				#  the image: 				jData["image"]
				#  ITP's version:			image=jData["version"]

				logger.debug("Copy Lean files")

				for thyfile in jData["files"]:
					content = jData["files"][thyfile]
					logger.debug ("writing file '" + path + thyfile.lower() + ".lean" + "'!")
					text_file = open(path + thyfile.lower() + ".lean", "w")
					text_file.write(content)
					text_file.close()

				logger.info("Compile Lean proof output")
				returncode = -1
				timedout = True
				timeout_sec = jData["timeout_all"]
				process = subprocess.Popen(compile_command)
				try:
					output, error = process.communicate(timeout=timeout_sec)
					timedout = False
					returncode = process.returncode
				except subprocess.TimeoutExpired:
					timedout = True

				checker_result = subprocess.run(check_command, stdout=subprocess.PIPE, encoding="utf-8")
				unknown_axiom = None
				for line in checker_result.stdout.splitlines():
					m = axiom_re.match(line)
					if m and m[1] not in ["propext", "classical.choice", "quot.sound"]:
						logger.info("UNKNOWN AXIOM: " + m[1])
						unknown_axiom = m[1]

				if timedout:
					logger.info("the checking process was killed !!")
					returncode = 8
					grader_msg = "the checking process was killed after %s !!" % timeout_sec
				elif unknown_axiom:
					returncode = 8
					grader_msg = "unknown axiom %s !!" % unknown_axiom
				else :
					# get the return message
					grader_msg = "OK"

				logger.info("-> Checking is done")

				logger.info("return code is:" + str(returncode))

				if returncode == 4:
					# sucessfully checked
					result = "1"
				else:
					# error occured or wrong
					result = "0"

				#### ONLY UNTIL HERE things are ProofAssistant-specific
				# now the following data should be set in these variables
				# the score (integer 0...1 as a string): 	result
				# Id of the submission:						submissionId
				# Id of the assessment:						assessmentId
				# some message (string):					grader_msg

				data=json.dumps({'result': result, 'sID': submissionId, 'aID': assessmentId, 'msg': grader_msg})

				logger.debug("put the result back to the server")
				response = requests.post(baseurl+puturl,data=data, headers=headers)

				if(response.ok):
					jData = json.loads(response.content)
					logger.debug("The response contains {0} properties".format(len(jData)))
					logger.debug("\n")
					for key in jData:
						logger.debug(key + " : " + jData[key])
				else:
					response.raise_for_status()
				logger.info("==================================================")
		else:
			try:
				my_response.raise_for_status()
			except requests.HTTPError as e:
				logger.debug(e)

		time.sleep(5)
