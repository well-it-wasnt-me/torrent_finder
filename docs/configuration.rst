Configuration
=============

The application reads a single JSON document (``config.json`` by default) that controls Torznab
queries, Transmission interaction, and log verbosity. Start from the sample file that ships in the
repository, then adjust the sections described below.

Example layout
--------------

.. code-block:: json

   {
     "torznab": {
       "url": "http://localhost:9117/jackett/torznab/all",
       "apikey": "CHANGE_ME",
       "categories": "2000"
     },
     "transmission": {
       "download_dir": "/path/to/save",
       "start": false,
       "use_rpc": true,
       "host": "localhost",
       "port": 9091,
       "username": "transmission",
       "password": "transmission"
     },
     "logging": {
       "level": "INFO"
     }
   }

Torznab section
---------------

url
   Base Torznab/Jackett endpoint (required).

apikey
   API key for the feed (required).

categories
   Optional comma-separated category identifiers to filter search results.

user_agent
   Custom HTTP ``User-Agent`` string. Defaults to ``Mozilla/5.0 (compatible; MagnetFinder/torznab-only 1.0)``.

request_timeout
   Timeout in seconds for Torznab requests (float, default ``12.0``).

sleep_between_requests
   Delay in seconds between Torznab requests to avoid hammering the indexer (float, default ``0.6``).

Transmission section
--------------------

download_dir
   Destination directory for completed or in-progress downloads (required).

start
   Whether torrents should start immediately after being added (default ``False``).

use_rpc
   Set to ``true`` to use the Transmission RPC interface; ``false`` switches to the ``transmission-remote`` CLI.

host, port
   Where Transmission is reachable. Defaults to ``localhost`` and ``9091``.

username, password
   RPC credentials when ``use_rpc`` is enabled. Leave ``null`` to connect without authentication.

auth
   ``user:pass`` credentials for the ``transmission-remote`` CLI.

Logging section
---------------

level
   One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``. Defaults to ``INFO``. Use ``--debug`` on the CLI
   to override this setting temporarily.

Applying overrides
------------------

Every command-line flag documented in :doc:`usage` maps to a configuration key. CLI overrides are
applied after ``config.json`` is loaded, letting you script temporary tweaks without editing the
JSON file.
