# Manage Moscow Audiobookshelf from the repository

Until `moscow` can be migrated as a fully managed host, manage Audiobookshelf through a self-contained Ubuntu/Docker bundle under `hosts/moscow/ubuntu/audiobookshelf/`. The repository is the sole source of truth for this container; Portainer may be used to observe it but not to edit, recreate, or update it, avoiding configuration drift without pretending that the rest of the host is managed.
