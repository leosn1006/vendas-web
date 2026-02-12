# vendas web
Hello World em Python (Flask) com deploy via Gunicorn + Nginx (80/443).

### Install
```
$ pip install -r requisitos.txt
```

### docker
```
docker compose up -d --build
docker compose ps
docker compose down
docker compose logs --tail=80 nginx
docker compose logs --tail=50 app
```
### ssl md5 da cadeia (crt + CAs) deve ser igual da key
```
openssl x509 -noout -modulus -in infra/nginx/certs/2810752673.crt | openssl md5
openssl rsa  -noout -modulus -in infra/nginx/certs/server.key     | openssl md5
```
#### git
```
 ssh-keygen -t ed25519 -C "leosn1006@gmail.com"
 eval "$(ssh-agent -s)"

 git remote set-url --add  git@github.com:leosn1006/vendas-web.git
```

### git com ssh
```
ssh-keygen -t ed25519 -C "seu-email@exemplo.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub

Coloque a chave no github key
```
