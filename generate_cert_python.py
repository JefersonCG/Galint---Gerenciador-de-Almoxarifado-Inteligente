"""Gera certificados SSL auto-assinados usando Python."""
import os
import sys
from datetime import datetime, timedelta

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("❌ Módulo 'cryptography' não encontrado!")
    print("📦 Instalando cryptography...")
    os.system(f"{sys.executable} -m pip install cryptography")
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

def generate_self_signed_cert():
    """Gera certificado e chave privada auto-assinados."""
    
    # Criar diretório certs se não existir
    cert_dir = "certs"
    if not os.path.exists(cert_dir):
        os.makedirs(cert_dir)
        print(f"✅ Diretório '{cert_dir}' criado.")
    
    # Gerar chave privada
    print("🔑 Gerando chave privada RSA 4096-bit...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend()
    )
    
    # Configurar detalhes do certificado
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "SP"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Sao Paulo"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "GALINT"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Development"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    # Criar certificado
    print("📜 Criando certificado auto-assinado...")
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
            x509.DNSName("10.0.0.245"),
            x509.IPAddress(IPv4Address("127.0.0.1")),
            x509.IPAddress(IPv4Address("10.0.0.245")),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256(), default_backend())
    
    # Salvar chave privada
    key_path = os.path.join(cert_dir, "key.pem")
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    print(f"✅ Chave privada salva em: {key_path}")
    
    # Salvar certificado
    cert_path = os.path.join(cert_dir, "cert.pem")
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"✅ Certificado salvo em: {cert_path}")
    
    print("\n" + "="*60)
    print("🎉 CERTIFICADOS GERADOS COM SUCESSO!")
    print("="*60)
    print(f"📁 Certificado: {cert_path}")
    print(f"🔐 Chave Privada: {key_path}")
    print(f"📅 Válido até: {(datetime.utcnow() + timedelta(days=365)).strftime('%d/%m/%Y')}")
    print("\n⚠️  AVISO: Certificados auto-assinados são APENAS para desenvolvimento!")
    print("   Para produção, use certificados válidos (Let's Encrypt, etc.)")
    print("="*60)

# Fix do import IPv4Address
from ipaddress import IPv4Address

if __name__ == "__main__":
    print("="*60)
    print("🔒 GERADOR DE CERTIFICADOS SSL AUTO-ASSINADOS")
    print("="*60)
    generate_self_signed_cert()
