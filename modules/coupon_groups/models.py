from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String
from database.models import Base

class CouponGroup(Base):
    __tablename__ = "coupon_groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class CouponGroupItem(Base):
    __tablename__ = "coupon_group_items"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("coupon_groups.id", ondelete="CASCADE"), nullable=False)
    code = Column(String, unique=True, nullable=False)
    amount = Column(Integer, default=0)
    days = Column(Integer, nullable=True)
    usage_limit = Column(Integer, nullable=False)
    usage_count = Column(Integer, default=0)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "code": self.code,
            "amount": self.amount,
            "days": self.days,
            "usage_limit": self.usage_limit,
            "usage_count": self.usage_count,
            "is_used": self.is_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class CouponGroupUsage(Base):
    __tablename__ = "coupon_group_usages"
    group_id = Column(Integer, ForeignKey("coupon_groups.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(BigInteger, primary_key=True)
    coupon_item_id = Column(Integer, ForeignKey("coupon_group_items.id", ondelete="CASCADE"), nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "group_id": self.group_id,
            "user_id": self.user_id,
            "coupon_item_id": self.coupon_item_id,
            "used_at": self.used_at.isoformat() if self.used_at else None,
        }
