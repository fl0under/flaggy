CC:=gcc
CFLAGS:=-O0 -fno-stack-protector -z execstack -no-pie
LDFLAGS:=

all: vuln

vuln: vuln.c
	  -o  $< 
	strip 

clean:
	rm -f vuln
