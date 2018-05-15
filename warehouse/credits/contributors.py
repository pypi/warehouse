from sqlalchemy import Column, Integer, String, Text

from warehouse import db


class Contributor(db.Model):

    __tablename__ = 'warehouse_contributors'

    contributor_login = Column(Text, primary_key=True, unique=True,
                               nullable=False)
    contributor_name = Column(Text, nullable=False)
    contributor_url = Column(Text, nullable=False)

    def __repr__(self):
        return "<{}(name='{}', url='{}')>".format(
                self.contributor_login, self.contributor_name,
                self.contributor_url)

