# GALINT Mobile - Endpoints Necessários no Backend

Para o app funcionar completamente, o backend Flask precisa ter os seguintes endpoints:

## 🔐 Autenticação

### POST /api/auth/login
```json
Request:
{
  "username": "usuario",
  "password": "senha"
}

Response:
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "username": "usuario",
    "nome": "Nome Completo",
    "setor": "Almoxarifado",
    "role": "admin"
  }
}
```

## 🏥 Health Check

### GET /api/health
```json
Response:
{
  "status": "ok",
  "message": "Server is running"
}
```

## 📦 Estoque

### GET /api/estoque
Query params: `?search=termo`

```json
Response:
[
  {
    "id": 1,
    "descricao": "Parafuso M10",
    "codigo_barras": "7891234567890",
    "categoria": "Ferramentas",
    "localizacao": "Prateleira A1",
    "marca": "Vonder",
    "quantidade": 150,
    "unidade": "UN"
  }
]
```

### GET /api/estoque/barcode/:barcode
```json
Response:
{
  "id": 1,
  "descricao": "Parafuso M10",
  "codigo_barras": "7891234567890",
  "quantidade": 150
}

Error (404):
{
  "message": "Item não encontrado"
}
```

### POST /api/estoque
```json
Request:
{
  "descricao": "Parafuso M10",
  "codigo_barras": "7891234567890",
  "categoria": "Ferramentas",
  "localizacao": "Prateleira A1",
  "marca": "Vonder",
  "quantidade": 150,
  "unidade": "UN"
}

Response:
{
  "id": 1,
  "message": "Item cadastrado com sucesso"
}
```

### PUT /api/estoque/:id
```json
Request:
{
  "descricao": "Parafuso M10",
  "quantidade": 200
}

Response:
{
  "message": "Item atualizado com sucesso"
}
```

## 🔧 Exemplo de Implementação Flask

```python
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import jwt
from datetime import datetime, timedelta

api = Blueprint('api_mobile', __name__, url_prefix='/api')

@api.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Server is running'})

@api.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        # Gerar token JWT
        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'])
        
        return jsonify({
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'nome': user.nome,
                'setor': user.setor,
                'role': user.role
            }
        })
    
    return jsonify({'message': 'Credenciais inválidas'}), 401

@api.route('/estoque', methods=['GET'])
@login_required
def get_estoque():
    search = request.args.get('search', '')
    
    query = InventoryItem.query
    if search:
        query = query.filter(
            InventoryItem.descricao.ilike(f'%{search}%')
        )
    
    items = query.all()
    return jsonify([item.to_dict() for item in items])

@api.route('/estoque/barcode/<barcode>', methods=['GET'])
@login_required
def get_by_barcode(barcode):
    item = InventoryItem.query.filter_by(codigo_barras=barcode).first()
    
    if item:
        return jsonify(item.to_dict())
    
    return jsonify({'message': 'Item não encontrado'}), 404

@api.route('/estoque', methods=['POST'])
@login_required
def create_item():
    data = request.get_json()
    
    item = InventoryItem(
        descricao=data.get('descricao'),
        codigo_barras=data.get('codigo_barras'),
        categoria=data.get('categoria'),
        localizacao=data.get('localizacao'),
        marca=data.get('marca'),
        quantidade=data.get('quantidade', 0),
        unidade=data.get('unidade', 'UN')
    )
    
    db.session.add(item)
    db.session.commit()
    
    return jsonify({
        'id': item.id,
        'message': 'Item cadastrado com sucesso'
    }), 201
```

## 🔒 Autenticação via Token

Adicione middleware para validar Bearer tokens:

```python
from functools import wraps
from flask import request, jsonify
import jwt

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].replace('Bearer ', '')
        
        if not token:
            return jsonify({'message': 'Token ausente'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
        except:
            return jsonify({'message': 'Token inválido'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated
```

Registre o blueprint no app:

```python
from galint_flask.views.api_mobile import api
app.register_blueprint(api)
```
