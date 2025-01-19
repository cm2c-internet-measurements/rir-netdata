build: Dockerfile
	echo Building image
	docker build -t carlosm3012/rir-netdata:v0.1.3 .

push: 
	echo Pushing image
	docker login
	docker push carlosm3012/rir-netdata:v0.1.3