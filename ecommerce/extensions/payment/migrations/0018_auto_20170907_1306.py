# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2017-09-07 13:06
from __future__ import unicode_literals

import django_extensions.db.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0017_auto_20170328_1445'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sdncheckfailure',
            name='created',
            field=django_extensions.db.fields.CreationDateTimeField(auto_now_add=True, verbose_name='created'),
        ),
        migrations.AlterField(
            model_name='sdncheckfailure',
            name='modified',
            field=django_extensions.db.fields.ModificationDateTimeField(auto_now=True, verbose_name='modified'),
        ),
    ]
