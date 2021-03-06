# -*- coding: utf-8 -*-
"""
    edacc.config
    ------------

    Web interface configuration.
"""

# Enable or disable printing of debug messages, disable in production use!
DEBUG = True

# Enable or disable memcached usage to cache expensive calculation results
CACHING = False
# Cache timeout in seconds
CACHE_TIMEOUT = 5
# Host and port of the memcache daemon
MEMCACHED_HOST = '127.0.0.1:11211'

# Directory the web application can use to save temporary files (required)
TEMP_DIR = '/tmp/edacc-webfrontend'

# Toggle Flask's error logging
LOGGING = False
LOG_FILE = '/srv/edacc_web/error.log'

# Use SSL for login pages etc.
ENABLE_SSL = False

# Enable use of piwik web analytics tool
PIWIK = False
# URL of the piwik installation to use (omit http://). Trailing slash is important!
PIWIK_URL = 'localhost/piwik/'

# Key used for signing cookies and salting crytpographic hashes. This has to
# be kept secret. It is impossible to authenticate stored passwords if this
# key differs from the one used to create the password hashes.
SECRET_KEY = '\xb4\xd5\xcd"\xd2Tm\xc4x*O:1\x85\x83\xf1\xf5\rc\xfc\xf8\xd0#|\xa5\xd8\xb1nM\xd9D\x97^\xb9M}e_\xb9az\xd5@\x7f\xadtLb\t\x9a\x85TJ\xf6\x1d\x92)1\x83\x17h\xbd\xfe\xc1\xa5\xe2\xae\xf0\xc8\x0c\xb8\xda7A\xab\xcc\xb2j\x13tz\xce\xa7a\xa8\xdcv\x9d$\xe9.\xd1\xd7\xf3U?AN\xf7\xa3'

DATABASE_DRIVER = 'mysql'
DATABASE_HOST = 'localhost'
DATABASE_PORT = 3306

# Used to log into the admin interface
ADMIN_PASSWORD = 'affe42'

# mail server that can be used by the web frontend
MAIL_SERVER = "smtp.googlemail.com"
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = "name@gmail.com"
MAIL_PASSWORD = "pw"
DEFAULT_MAIL_SENDER = "bla@gmail.com"

# folder used to upload benchmarks to
UPLOAD_FOLDER = "/tmp"

# folder with external binaries etc.
CONTRIB_DIR = "contrib"

# List of databases this server connects to at startup
# Format: Tuples of username, password, database, label (used on the pages), hidden
DEFAULT_DATABASES = (
    ('username', 'password', 'db name', 'db label', False),
)

hidden_experiments = dict()

# override config with local config, if present
try:
    from edacc.local_config import *
except ImportError:
    pass
