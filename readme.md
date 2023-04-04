## Import BDNB pour exploration
- Copier le dump dans le répertoire source_data
- Se connecter au terminal du container batid-db-1
- aller dans le répertoire /usr/src/import_data
- exécutr le command ci-dessous : 

```bash 
psql -U postgres -d postgres < bdnb.sql
```

## Contributing 

All types of contributions are welcome ! 

A small guide is available in [`CONTRIBUTING`](CONTRIBUTING.md) to contribute to the project !
