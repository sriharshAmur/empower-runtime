#!/usr/bin/env python3
#
# Copyright (c) 2022 Roberto Riggio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""Alert class."""

import logging

from pymodm import MongoModel, fields
from empower_core.serialize import serializable_dict


@serializable_dict
class Alert(MongoModel):
    """Base Alert class.

    Attributes:
        uuid: This Device MAC address (EtherAddress)
        alert: A human-radable description of this Device (str)
        subscriptions: the list of MAC subscribed to this alert
        log: logging facility
    """

    uuid = fields.UUIDField(primary_key=True)
    alert = fields.CharField(required=True)
    subscriptions = fields.CharField(required=False)

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

        self.log = logging.getLogger("%s" % self.__class__.__module__)

    def to_dict(self):
        """Return JSON-serializable representation of the object."""

        out = {
            'uuid': self.uuid,
            'alert': self.alert,
            'subscriptions': self.subscriptions
        }

        return out

    def to_str(self):
        """Return an ASCII representation of the object."""

        return "%s - %s" % (self.uuid, self.alert)

    def __str__(self):
        return self.to_str()

    def __hash__(self):
        return hash(self.uuid)

    def __eq__(self, other):
        if isinstance(other, Alert):
            return self.uuid == other.uuid
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return self.__class__.__name__ + "('" + self.to_str() + "')"
