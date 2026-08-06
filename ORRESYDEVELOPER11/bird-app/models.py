from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

park_birds = db.Table('park_birds',
    db.Column('park_id', db.Integer, db.ForeignKey('park.id')),
    db.Column('bird_id', db.Integer, db.ForeignKey('bird.id'))
)

class Habitat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    climate = db.Column(db.String(200))
    ecosystem_data = db.Column(db.Text)
    image_url = db.Column(db.String(300))
    icon = db.Column(db.String(50))
    birds = db.relationship('Bird', backref='habitat', lazy=True)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'slug': self.slug,
            'description': self.description, 'climate': self.climate,
            'ecosystem_data': self.ecosystem_data, 'image_url': self.image_url,
            'icon': self.icon,
            'bird_count': len(self.birds)
        }

class Bird(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(150), nullable=False)
    scientific_name = db.Column(db.String(150))
    habitat_id = db.Column(db.Integer, db.ForeignKey('habitat.id'))
    migration_pattern = db.Column(db.String(200))
    conservation_status = db.Column(db.String(50))
    description = db.Column(db.Text)
    image_url = db.Column(db.String(300))
    audio_url = db.Column(db.String(300))
    region = db.Column(db.String(100))

    def to_dict(self):
        return {
            'id': self.id, 'common_name': self.common_name,
            'scientific_name': self.scientific_name,
            'habitat': self.habitat.name if self.habitat else None,
            'migration_pattern': self.migration_pattern,
            'conservation_status': self.conservation_status,
            'description': self.description, 'image_url': self.image_url,
            'audio_url': self.audio_url, 'region': self.region
        }

class Park(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    country = db.Column(db.String(100))
    region = db.Column(db.String(100))
    description = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    habitat_type = db.Column(db.String(100))
    best_visit_months = db.Column(db.String(200))
    conservation_status = db.Column(db.String(50))
    image_url = db.Column(db.String(300))
    area_km2 = db.Column(db.Float)
    birds = db.relationship('Bird', secondary=park_birds, backref='parks')

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'country': self.country,
            'region': self.region, 'description': self.description,
            'latitude': self.latitude, 'longitude': self.longitude,
            'habitat_type': self.habitat_type,
            'best_visit_months': self.best_visit_months,
            'conservation_status': self.conservation_status,
            'image_url': self.image_url, 'area_km2': self.area_km2,
            'bird_count': len(self.birds),
            'birds': [b.common_name for b in self.birds[:5]]
        }

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    slug = db.Column(db.String(300), unique=True)
    content = db.Column(db.Text)
    category = db.Column(db.String(100))
    image_url = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_time = db.Column(db.Integer)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'slug': self.slug,
            'content': self.content, 'category': self.category,
            'image_url': self.image_url,
            'created_at': self.created_at.strftime('%B %d, %Y'),
            'read_time': self.read_time
        }

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_type = db.Column(db.String(30), nullable=False)
    item_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    park_id = db.Column(db.Integer, db.ForeignKey('park.id'), nullable=False)
    visited_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    park_id = db.Column(db.Integer, db.ForeignKey('park.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='reviews')
    park = db.relationship('Park', backref='reviews')

class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    bird_id = db.Column(db.Integer, db.ForeignKey('bird.id'), nullable=True)
    image_path = db.Column(db.String(300), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    model_name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(40), default='completed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='predictions')
    bird = db.relationship('Bird', backref='predictions')


class Sighting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    bird_id = db.Column(db.Integer, db.ForeignKey('bird.id'), nullable=True)
    image_path = db.Column(db.String(300))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    confidence = db.Column(db.Float)
    species_guess = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='sightings')
    bird = db.relationship('Bird', backref='sightings')

    def to_dict(self):
        return {
            "id": self.id,
            "bird_id": self.bird_id,
            "species_guess": self.species_guess or (self.bird.common_name if self.bird else None),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "confidence": self.confidence,
            "image_path": self.image_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
