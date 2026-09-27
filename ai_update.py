#!/usr/bin/env python3
"""Compatibility entrypoint: execute the repository Agent Skill and apply its proposal."""
from scout import prepare, apply
from agent_refresh import run

if __name__ == '__main__':
    prepare()
    run()
    apply()
