#!/usr/bin/env bash

poetry export --without-hashes --format=requirements.txt >requirements.txt
