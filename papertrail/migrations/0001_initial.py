# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Entry'
        db.create_table('papertrail_entry', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('timestamp', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('type', self.gf('django.db.models.fields.CharField')(max_length=50)),
            ('message', self.gf('django.db.models.fields.CharField')(max_length=255)),
            ('data', self.gf('jsonfield.fields.JSONField')(null=True)),
        ))
        db.send_create_signal('papertrail', ['Entry'])

        # Adding model 'EntryRelatedObject'
        db.create_table('papertrail_entryrelatedobject', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('entry', self.gf('django.db.models.fields.related.ForeignKey')(related_name='related_objects', to=orm['papertrail.Entry'])),
            ('relation_name', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('related_content_type', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['contenttypes.ContentType'])),
            ('related_id', self.gf('django.db.models.fields.PositiveIntegerField')()),
        ))
        db.send_create_signal('papertrail', ['EntryRelatedObject'])


    def backwards(self, orm):
        # Deleting model 'Entry'
        db.delete_table('papertrail_entry')

        # Deleting model 'EntryRelatedObject'
        db.delete_table('papertrail_entryrelatedobject')


    models = {
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'papertrail.entry': {
            'Meta': {'ordering': "['-timestamp']", 'object_name': 'Entry'},
            'data': ('jsonfield.fields.JSONField', [], {'null': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'message': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'timestamp': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'type': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'papertrail.entryrelatedobject': {
            'Meta': {'object_name': 'EntryRelatedObject'},
            'entry': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'related_objects'", 'to': "orm['papertrail.Entry']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'related_content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'related_id': ('django.db.models.fields.PositiveIntegerField', [], {}),
            'relation_name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        }
    }

    complete_apps = ['papertrail']