.PHONY: server clean plugins
server:
	lektor server
clean:
	lektor clean --yes -v
plugins:
	lektor plugins flush-cache && lektor plugins list
