"""
	Script for generating smart playlists based on a seeding track and last.fm api
	Created by: ErlendSB
"""

import os
import random
import difflib
import httplib, urllib, urllib2
import sys, time
import threading, thread
import xbmc, xbmcgui, xbmcaddon
import unicodedata
from urllib import quote_plus, unquote_plus
import re
from os.path import exists
from os import remove
if sys.version_info < (2, 7):
    import simplejson
else:
    import json as simplejson

__settings__ = xbmcaddon.Addon(id='script.lastfmplaylistgeneratorPM')
__addonversion__ = __settings__.getAddonInfo('version')
__cwd__          = __settings__.getAddonInfo('path')

def log(message):
    xbmc.log(msg=message)
class MyPlayer( xbmc.Player ) :
	countFoundTracks = 0
	addedTracks = []
	currentSeedingTrack = 0
	firstRun = 0
	dbtype = 'sqlite3'
	timeStarted = time.time()
	SCRIPT_NAME = "LAST.FM Playlist Generator"
	
	allowtrackrepeat =  __settings__.getSetting( "allowtrackrepeat" )
	preferdifferentartist = __settings__.getSetting( "preferdifferentartist" )
	numberoftrackstoadd = ( 1, 3, 5, 10, )[ int( __settings__.getSetting( "numberoftrackstoadd" ) ) ]
	delaybeforesearching= ( 2, 10, 30, )[ int( __settings__.getSetting( "delaybeforesearching" ) ) ]
	limitlastfmresult= ( 50, 100, 250, )[ int( __settings__.getSetting( "limitlastfmresult" ) ) ]
	minimalplaycount= ( 50, 100, 250, 500, )[ int( __settings__.getSetting( "minimalplaycount" ) ) ]
	minimalmatching= ( 1, 2, 5, 10, 20, )[ int( __settings__.getSetting( "minimalmatching" ) ) ]
	mode= ( "Similar tracks", "Top tracks of similar artist", "Custom", )[ int(__settings__.getSetting( "mode" ) ) ]
	timer = None


	#apiPath = "http://ws.audioscrobbler.com/2.0/?api_key=71e468a84c1f40d4991ddccc46e40f1b"
	apiPath = "http://ws.audioscrobbler.com/2.0/?api_key=3ae834eee073c460a250ee08979184ec"
	
	def __init__ ( self ):
		if not os.path.exists(xbmc.translatePath("special://userdata/advancedsettings.xml")):
			self.dbtype = 'sqlite3'
		else:
			from xml.etree.ElementTree import ElementTree
			advancedsettings = ElementTree()
			advancedsettings.parse(xbmc.translatePath("special://userdata/advancedsettings.xml"))
			settings = advancedsettings.getroot().find("musicdatabase")
			if settings is not None:
				for setting in settings:
					if setting.tag == 'type':
						self.dbtype = setting.text
			else:
				self.dbtype = 'sqlite3'
		xbmc.Player.__init__( self )
		xbmc.PlayList(0).clear()
		self.firstRun = 1
		BASE_RESOURCE_PATH = os.path.join( __cwd__, "resources" )
		process = os.path.join( BASE_RESOURCE_PATH , "pm.pid")
		removeauto('lastfmplaylistgeneratorpm')
		addauto("if os.path.exists('" + os.path.normpath(process).replace('\\','\\\\') + "'):#lastfmplaylistgeneratorpm\n\tos.remove('" + os.path.normpath(process).replace('\\','\\\\') + "')","lastfmplaylistgeneratorpm")
		xbmc.executebuiltin("Notification(" + self.SCRIPT_NAME+",Start by playing a song)")
	
	def startPlayBack(self):
		print "[LFM PLG(PM)] onPlayBackStarted started"
		if xbmc.Player().isPlayingAudio() == True:
			currentlyPlayingTitle = xbmc.Player().getMusicInfoTag().getTitle()
			currentlyPlayingArtist = xbmc.Player().getMusicInfoTag().getArtist()
			print "[LFM PLG(PM)] " + currentlyPlayingArtist + " - " + currentlyPlayingTitle + " started playing"
			self.countFoundTracks = 0
			if (self.firstRun == 1):
				self.firstRun = 0
				album = xbmc.Player().getMusicInfoTag().getAlbum()
				cache_name = xbmc.getCacheThumbName(os.path.dirname(xbmc.Player().getMusicInfoTag().getURL()))
				print "[LFM PLG(PM)] Playing file: %s" % xbmc.Player().getMusicInfoTag().getURL()
				thumb = "special://profile/Thumbnails/Music/%s/%s" % ( cache_name[:1], cache_name, )
				duration = xbmc.Player().getMusicInfoTag().getDuration()
				fanart = ""
				listitem = self.getListItem(currentlyPlayingTitle,currentlyPlayingArtist,album,thumb,fanart,duration)
				xbmc.PlayList(0).clear()
				xbmc.executebuiltin('XBMC.ActivateWindow(10500)')
				xbmc.PlayList(0).add(url= xbmc.Player().getMusicInfoTag().getURL(), listitem = listitem)
				self.addedTracks += [self.unicode_normalize_string(xbmc.Player().getMusicInfoTag().getURL())]
			self.main_similarTracks(currentlyPlayingTitle,currentlyPlayingArtist)

	def onPlayBackStarted(self):
		print "[LFM PLG(PM)] onPlayBackStarted waiting:  " + str(self.delaybeforesearching) +" seconds"
		if (self.timer is not None and self.timer.isAlive()):
			self.timer.cancel()
			
		self.timer = threading.Timer(self.delaybeforesearching,self.startPlayBack)
		self.timer.start()
	
	def unicode_normalize_string(self, text):
		return unicodedata.normalize('NFD', unicode(text, 'utf-8')).encode('ascii', 'ignore').upper().replace("-","")	
	
	def fetch_searchTrack(self, currentlyPlayingTitle, currentlyPlayingArtist ):
		apiMethod = "&method=track.search&limit=" + str(self.limitlastfmresult)

		# The url in which to use
		Base_URL = self.apiPath + apiMethod + "&artist=" + urllib.quote_plus(self.unicode_normalize_string(currentlyPlayingArtist)) + "&track=" + urllib.quote_plus(self.unicode_normalize_string(currentlyPlayingTitle))
		WebSock = urllib.urlopen(Base_URL)  # Opens a 'Socket' to URL
		print "[LFM PLG(PM)] Request : " + Base_URL
		WebHTML = WebSock.read()            # Reads Contents of URL and saves to Variable
		WebSock.close()                     # Closes connection to url
		
		searchTracks = re.findall("<track>.*?<name>(.+?)</name>.*?<artist>(.+?)</artist>.*?<listeners>(.+?)</listeners>.*?</track>", WebHTML, re.DOTALL )		
		foundTracks = []
		
		for foundTrackName, foundArtistName, foundListeners in searchTracks :
			if(foundListeners > self.minimalplaycount):
				foundFullName = foundArtistName + " " + foundTrackName
				currentFullName = currentlyPlayingArtist + " " + currentlyPlayingTitle
				fullRatio = difflib.SequenceMatcher(None, foundFullName, currentFullName).ratio()

				if(fullRatio > 0.5):
					foundTracks.append([foundTrackName, foundArtistName])
					print "[LFM PLG(PM)] Found Similar Track Name : " + foundTrackName + " by: " + foundArtistName
		
		return foundTracks

	def fetch_similarArtists( self, currentlyPlayingArtist ):
		apiMethod = "&method=artist.getsimilar&limit=50"

		# The url in which to use
		Base_URL = self.apiPath + apiMethod + "&artist=" + urllib.quote_plus(self.unicode_normalize_string(currentlyPlayingArtist))
		WebSock = urllib.urlopen(Base_URL)  # Opens a 'Socket' to URL
		print "[LFM PLG(PM)] Request : " + Base_URL		
		WebHTML = WebSock.read()            # Reads Contents of URL and saves to Variable
		WebSock.close()                     # Closes connection to url
	
		similarArtists = re.findall("<artist>.*?<name>(.+?)</name>.*?<mbid>(.+?)</mbid>.*?<match>(.+?)</match>.*?</artist>", WebHTML, re.DOTALL )
		similarArtists = [x for x in similarArtists if float(x[2]) > (float(self.minimalmatching)/100.0)]			
		return similarArtists
	
	def find_Artist(self, artistName):
		json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "AudioLibrary.GetArtists", "params": { "filter": {"field":"artist","operator":"is","value":"%s"} }, "id": 1}' % (artistName)) 
		json_query = unicode(json_query, 'utf-8', errors='ignore')
		json_response = simplejson.loads(json_query)
		if json_response.has_key('result') and json_response['result'] != None and json_response['result'].has_key('artists') :
			return True
		return False
	
	def fetch_topTracksOfArtist( self, mbIdArtist ):
		apiMethod = "&method=artist.gettoptracks&limit=20"

		# The url in which to use
		Base_URL = self.apiPath + apiMethod + "&mbid=" + urllib.quote_plus(mbIdArtist)
		WebSock = urllib.urlopen(Base_URL)  # Opens a 'Socket' to URL
		print "[LFM PLG(PM)] Request : " + Base_URL		
		WebHTML2 = WebSock.read()            # Reads Contents of URL and saves to Variable
		WebSock.close()                     # Closes connection to url
		topTracks = re.findall("<track rank=.+?>.*?<name>(.+?)</name>.*?<playcount>(.+?)</playcount>.*?<listeners>(.+?)</listeners>.*?<artist>.*?<name>(.+?)</name>.*?</artist>.*?</track>", WebHTML2, re.DOTALL )
		print "[LFM PLG(PM)] Count: " + str(len(topTracks))
		topTracks = [x for x in topTracks if int(x[1]) > self.minimalplaycount]		
		return topTracks	
		
	def fetch_similarTracks( self, currentlyPlayingTitle, currentlyPlayingArtist ):
		apiMethod = "&method=track.getsimilar&limit=" + str(self.limitlastfmresult)

		# The url in which to use
		Base_URL = self.apiPath + apiMethod + "&artist=" + urllib.quote_plus(self.unicode_normalize_string(currentlyPlayingArtist)) + "&track=" + urllib.quote_plus(self.unicode_normalize_string(currentlyPlayingTitle))
		WebSock = urllib.urlopen(Base_URL)  # Opens a 'Socket' to URL
		print "[LFM PLG(PM)] Request : " + Base_URL		
		WebHTML = WebSock.read()            # Reads Contents of URL and saves to Variable
		WebSock.close()                     # Closes connection to url

		similarTracks = re.findall("<track>.*?<name>(.+?)</name>.*?<playcount>(.+?)</playcount>.*?<match>(.+?)</match>.*?<artist>.*?<name>(.+?)</name>.*?</artist>.*?</track>", WebHTML, re.DOTALL )
		similarTracks = [x for x in similarTracks if int(x[1]) > self.minimalplaycount]	
		similarTracks = [x for x in similarTracks if float(x[2]) > (float(self.minimalmatching)/100.0)]			
		return similarTracks
		
	def main_similarTracks( self, currentlyPlayingTitle, currentlyPlayingArtist ):
		countTracks = 0
		similarTracks = []
		if(self.mode == "Similar tracks" or self.mode == "Custom"):
			similarTracks += self.fetch_similarTracks(currentlyPlayingTitle, currentlyPlayingArtist)
			countTracks = len(similarTracks)			
		if(self.mode == "Top tracks of similar artist" or (self.mode == "Custom" and countTracks < 10)):
			similarArtists = self.fetch_similarArtists(currentlyPlayingArtist)
			print "[LFM PLG(PM)] Nb Similar Artists : " + str(len(similarArtists))
			for similarArtistName, mbid, matchValue in similarArtists:
				if self.find_Artist(similarArtistName):
					similarTracks += self.fetch_topTracksOfArtist(mbid)
				
		foundArtists = []
		countTracks = len(similarTracks)
		print "[LFM PLG(PM)] Count: " + str(countTracks)
		#if(countTracks < 10):
		#	print "[LFM PLG(PM)] Find Similar Track Name"
		#	listSearchResult = []
		#	listSearchResult = self.fetch_searchTrack(currentlyPlayingTitle, currentlyPlayingArtist)
		#	countFoundTracks = len(listSearchResult)
		#	print "[LFM PLG(PM)] Find Similar Track Name - Count: " + str(countFoundTracks)
		#	for searchTrackName, searchArtistName in listSearchResult:
		#		similarTracks += self.fetch_similarTracks(searchTrackName, searchArtistName)
		#	countTracks = len(similarTracks)
		#	print "[LFM PLG(PM)] Find Similar Track - Count: " + str(countTracks)		

		random.shuffle(similarTracks)
		selectedArtist = []
		for similarTrackName, playCount, matchValue, similarArtistName in similarTracks:
			similarTrackName = similarTrackName.replace("+"," ").replace("("," ").replace(")"," ").replace("&quot","''").replace("&amp;","and")
			similarArtistName = similarArtistName.replace("+"," ").replace("("," ").replace(")"," ").replace("&quot","''").replace("&amp;","and")
			log("Looking for: " + similarTrackName + " - " + similarArtistName + " - " + matchValue + "/" + playCount)			
			json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "AudioLibrary.GetSongs", "params": { "properties": ["title", "artist", "album", "file", "thumbnail", "duration", "fanart"], "limits": {"end":1}, "sort": {"method":"random"}, "filter": { "and":[{"field":"title","operator":"is","value":"%s"},{"field":"artist","operator":"is","value":"%s"}] } }, "id": 1}' % (similarTrackName, similarArtistName)) 
			json_query = unicode(json_query, 'utf-8', errors='ignore')
			json_response = simplejson.loads(json_query)
			if not(json_response.has_key('result')) or json_response['result'] == None or not(json_response['result'].has_key('songs')):
				json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "AudioLibrary.GetSongs", "params": { "properties": ["title", "artist", "album", "file", "thumbnail", "duration", "fanart"], "limits": {"end":1}, "sort": {"method":"random"}, "filter": { "and":[{"field":"title","operator":"contains","value":"%s"},{"field":"artist","operator":"contains","value":"%s"}] } }, "id": 1}' % (similarTrackName, similarArtistName)) 
				json_query = unicode(json_query, 'utf-8', errors='ignore')
				json_response = simplejson.loads(json_query)
				
			# separate the records
			if json_response.has_key('result') and json_response['result'] != None and json_response['result'].has_key('songs'):
				count = 0
				for item in json_response['result']['songs']:
					count += 1
					artist = ""
					if (len(item["artist"]) > 0):
						artist = item["artist"][0]
					trackTitle = item["title"]
					album = item["album"]
					trackPath = item["file"]
					thumb = item["thumbnail"]
					duration = int(item["duration"])
					fanart = item["fanart"]
					if(artist not in selectedArtist):
						selectedArtist.append(artist)
						print "[LFM PLG(PM)] Found: " + trackTitle.encode('utf-8') + " by: " + artist.encode('utf-8')
						if ((self.allowtrackrepeat == "true" or self.allowtrackrepeat == 1) or (self.unicode_normalize_string(trackPath.encode('utf-8')) not in self.addedTracks)):
							if ((self.preferdifferentartist != "true" and self.preferdifferentartist != 1) or (self.unicode_normalize_string(similarArtistName) not in foundArtists)):
								listitem = self.getListItem(trackTitle,artist,album,thumb,fanart,duration)
								xbmc.PlayList(0).add(url=trackPath, listitem=listitem)
								print "[LFM PLG(PM)] Add track : " + trackTitle.encode('utf-8') + " by: " + artist.encode('utf-8')
								self.addedTracks += [self.unicode_normalize_string(trackPath.encode('utf-8'))]
								xbmc.executebuiltin("Container.Refresh")
								self.countFoundTracks += 1
								if (self.unicode_normalize_string(similarArtistName) not in foundArtists):
									foundArtists += [self.unicode_normalize_string(similarArtistName)]

				if (self.countFoundTracks >= self.numberoftrackstoadd):
					break
			
		if (self.countFoundTracks == 0):
			time.sleep(3)
			#self.firstRun = 1
			log("[LFM PLG(PM)] None found")
			xbmc.executebuiltin("Notification(" + self.SCRIPT_NAME+",No similar tracks were found)")
			return False
			
		xbmc.executebuiltin('SetCurrentPlaylist(0)')
		
	def getListItem(self, trackTitle, artist, album, thumb, fanart,duration):
		listitem = xbmcgui.ListItem(trackTitle)
		if (fanart == ""):
			cache_name = xbmc.getCacheThumbName( str(artist) )
			fanart = "special://profile/Thumbnails/Music/%s/%s" % ( "Fanart", cache_name, )
		listitem.setProperty('fanart_image',fanart)
		listitem.setInfo('music', { 'title': trackTitle, 'artist': artist, 'album': album, 'duration': duration })
		listitem.setThumbnailImage(thumb)
		#log("[LFM PLG(PM)] Fanart:%s" % fanart)
		return listitem

def addauto(newentry, scriptcode):
	autoexecfile = xbmc.translatePath('special://home/userdata/autoexec.py')
	#autoexecfile = "special://masterprofile/autoexec.py"
	if exists(autoexecfile):
		fh = open(autoexecfile)
		lines = []
		for line in fh.readlines():
			lines.append(line)
		lines.append("import time" + "#" + scriptcode + "\n")
		lines.append("time.sleep(2)" + "#" + scriptcode + "\n")
		lines.append(newentry + "#" + scriptcode + "\n")
		fh.close()
		f = open(autoexecfile, "w")
		if not "import xbmc\n" in lines:
			f.write("import xbmc" + "#" + scriptcode + "\n")
		if not "import os\n" in lines:
			f.write("import os" + "#" + scriptcode + "\n")
		f.writelines(lines)
		f.close()
	else:
		f = open(autoexecfile, "w")
		f.write("import time" + "#" + scriptcode + "\n")
		f.write("time.sleep(2)" + "#" + scriptcode + "\n")
		f.write("import os" + "#" + scriptcode + "\n")
		f.write("import xbmc" + "#" + scriptcode + "\n")
		f.write(newentry + "#" + scriptcode + "\n")
		f.close()

def removeauto(scriptcode):
	autoexecfile = xbmc.translatePath('special://home/userdata/autoexec.py')
	#autoexecfile = "special://masterprofile/autoexec.py"
	if exists(autoexecfile):
		fh = open(autoexecfile)
		lines = [ line for line in fh if not line.strip().endswith("#" + scriptcode) ]
		fh.close()
		f = open(autoexecfile, "w")
		f.writelines(lines)
		f.close()
		
BASE_RESOURCE_PATH = os.path.join( __cwd__, "resources" )

process = os.path.join( BASE_RESOURCE_PATH , "pm.pid")
p=MyPlayer()
while(1):
	if os.path.exists(process):
		if (xbmc.abortRequested):
			os.remove(process)
			print "[LFM PLG(PM)] deleting pid"
		xbmc.sleep(500)
	else:
		break