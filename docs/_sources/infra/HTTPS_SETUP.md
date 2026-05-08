# Guia de Configuração HTTPS para GALINT Flask

## 📋 Índice
- [Desenvolvimento (Certificados Auto-Assinados)](#desenvolvimento)
- [Produção com Waitress](#produção-com-waitress)
- [Produção com Nginx Reverse Proxy](#produção-com-nginx)
- [Produção com IIS Reverse Proxy](#produção-com-iis)

---

## 🔧 Desenvolvimento

### Opção 1: Certificados Auto-Assinados (Rápido)

1. **Gerar certificados:**
   ```powershell
   .\generate_cert.ps1
   ```

2. **Executar com HTTPS:**
   ```powershell
   .\run_https.ps1
   ```

3. **Acessar:**
   - URL: `https://10.0.0.245:5443`
   - Navegador mostrará aviso de segurança (normal para cert auto-assinado)
   - Aceite o risco e continue

### Opção 2: Modificar app.py diretamente

Edite `app.py`:
```python
if __name__ == "__main__":
    app.run(
        host="10.0.0.245", 
        port=5443, 
        debug=True,
        ssl_context=('certs/cert.pem', 'certs/key.pem')
    )
```

---

## 🚀 Produção

### **RECOMENDADO: Usar Reverse Proxy**

Em produção, **NÃO execute Flask diretamente com SSL**. Use um servidor web como proxy reverso.

### Opção A: Waitress com SSL (Simples, Windows-friendly)

1. **Instalar Waitress:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   pip install waitress
   ```

2. **Criar certificado de produção** (Let's Encrypt recomendado):
   ```powershell
   # Para Windows, use win-acme:
   # https://www.win-acme.com/
   ```

3. **Criar script de produção SSL:**
   Crie `start_production_https.ps1`:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   
   $env:FLASK_ENV = "production"
   
   python -c "
   from waitress import serve
   from galint_flask import create_app
   
   app = create_app()
   serve(app, 
       host='0.0.0.0', 
       port=443,
       url_scheme='https',
       ident='GALINT'
   )
   "
   ```

   **Nota:** Waitress não gerencia SSL diretamente. Use com reverse proxy.

### Opção B: Nginx Reverse Proxy (RECOMENDADO)

1. **Instalar Nginx:**
   ```powershell
   # Baixe de: https://nginx.org/en/download.html
   ```

2. **Configurar Nginx** (`nginx.conf`):
   ```nginx
   server {
       listen 443 ssl;
       server_name seu-dominio.com;

       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers HIGH:!aNULL:!MD5;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto https;
       }
   }

   # Redirecionar HTTP para HTTPS
   server {
       listen 80;
       server_name seu-dominio.com;
       return 301 https://$server_name$request_uri;
   }
   ```

3. **Executar:**
   ```powershell
   # Terminal 1: Flask
   .\start_production.ps1

   # Terminal 2: Nginx
   nginx
   ```

### Opção C: IIS Reverse Proxy (Windows Server)

1. **Instalar IIS e módulos:**
   - URL Rewrite Module
   - Application Request Routing (ARR)

2. **Configurar certificado no IIS:**
   - Painel IIS → Server Certificates → Import
   - Ou usar certificado do Let's Encrypt

3. **Criar Reverse Proxy:**
   
   Crie `web.config` na raiz:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <configuration>
       <system.webServer>
           <rewrite>
               <rules>
                   <rule name="ReverseProxyInboundRule" stopProcessing="true">
                       <match url="(.*)" />
                       <action type="Rewrite" url="http://localhost:5000/{R:1}" />
                       <serverVariables>
                           <set name="HTTP_X_FORWARDED_PROTO" value="https" />
                       </serverVariables>
                   </rule>
               </rules>
           </rewrite>
       </system.webServer>
   </configuration>
   ```

4. **No IIS Manager:**
   - Bind HTTPS na porta 443
   - Selecione seu certificado SSL

---

## 🔒 Obtendo Certificados SSL Válidos

### Let's Encrypt (Grátis)

**Windows:**
```powershell
# Usar win-acme (anteriormente letsencrypt-win-simple)
# Download: https://www.win-acme.com/

# Executar e seguir wizard:
wacs.exe
```

**Linux (Certbot):**
```bash
sudo apt install certbot
sudo certbot certonly --standalone -d seu-dominio.com
```

### Certificado Comercial

1. Compre de CA confiável (DigiCert, GlobalSign, etc.)
2. Gere CSR (Certificate Signing Request)
3. Envie para CA
4. Instale certificado retornado

---

## ✅ Checklist de Segurança

- [ ] Certificados válidos (não auto-assinados) em produção
- [ ] TLS 1.2+ habilitado
- [ ] HTTP redireciona para HTTPS
- [ ] Headers de segurança configurados
- [ ] Firewall permite porta 443
- [ ] Renovação automática de certificados
- [ ] HSTS (HTTP Strict Transport Security) ativado

---

## 🔍 Testando

```powershell
# Verificar certificado
openssl s_client -connect 10.0.0.245:5443 -showcerts

# Testar conexão
curl -k https://10.0.0.245:5443

# No navegador
https://10.0.0.245:5443
```

---

## 🐛 Troubleshooting

### "Certificate verify failed"
- Certificado auto-assinado precisa ser aceito manualmente
- Use `-k` no curl ou aceite no navegador

### "Port 443 already in use"
- Outro serviço usando porta 443 (IIS, outro web server)
- Use `netstat -ano | findstr :443` para identificar

### "pyOpenSSL not found"
```powershell
pip install pyOpenSSL
```

### Headers X-Forwarded-Proto não funcionam
Adicione ao Flask (`config.py`):
```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
```

---

## 📚 Recursos

- [Flask SSL Context](https://flask.palletsprojects.com/en/latest/api/#flask.Flask.run)
- [Let's Encrypt](https://letsencrypt.org/)
- [Nginx SSL Config](https://nginx.org/en/docs/http/configuring_https_servers.html)
- [IIS URL Rewrite](https://www.iis.net/downloads/microsoft/url-rewrite)
