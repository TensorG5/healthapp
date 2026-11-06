IMAGE ?= healthapp:1.0

.PHONY: build run deploy status logs clean

build:
	docker build -t $(IMAGE) .

run: build
	sudo install -d -o 10001 -g 10001 -m 755 /var/log/healthapp
	docker run --rm --init --name healthapp-dev \
	    --env-file deploy/healthapp.env --memory 128m \
	    -p 8080:8080 -v /var/log/healthapp:/var/log/healthapp $(IMAGE)

deploy: build
	sudo install -d -o 10001 -g 10001 -m 755 /var/log/healthapp
	sudo install -d -m 755 /etc/healthapp
	sudo test -f /etc/healthapp/healthapp.env || sudo install -m 644 deploy/healthapp.env /etc/healthapp/healthapp.env
	sudo install -m 644 deploy/healthapp.service /etc/systemd/system/healthapp.service
	sudo install -m 644 deploy/logrotate.conf /etc/logrotate.d/healthapp
	sudo systemctl daemon-reload
	sudo systemctl enable healthapp
	sudo systemctl restart healthapp

status:
	systemctl status healthapp --no-pager

logs:
	sudo tail -n 20 /var/log/healthapp/access.log

clean:
	-sudo systemctl stop healthapp
	-docker rmi $(IMAGE)
