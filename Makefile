libio.so: io.c
	gcc -fPIC -shared -o libio.so io.c
