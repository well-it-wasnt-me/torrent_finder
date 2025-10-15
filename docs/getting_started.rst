Getting started
===============

This project targets Python 3.10+ and assumes you have a Torznab/Jackett instance as well as
Transmission available somewhere on your network. The steps below get the repository ready for use
or further hacking.

Prerequisites
-------------
- Python 3.10 or newer.
- Access to a Torznab/Jackett feed with a valid API key.
- Transmission installed locally or reachable over the network (RPC or ``transmission-remote``).

Create an isolated environment
------------------------------

.. code-block:: bash

   python3 -m venv .venv
   source .venv/bin/activate

Install dependencies
--------------------

.. code-block:: bash

   pip install --upgrade pip
   pip install -r requirements.txt

Set up configuration
--------------------

Start from the sample file, then see :doc:`configuration` for every available option.

.. code-block:: bash

   cp config.example.json config.json

Verify the installation
-----------------------

Run the unit tests to confirm the environment is wired correctly.

.. code-block:: bash

   pytest

From here you are ready to explore :doc:`usage` or build out your own automation on top of the API.
