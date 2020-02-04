# Readme des traitements panoramas

## Mis en oeuvre.

Tout est passé sur python 3.7. Si cette version n'est pas disponible, utiliser un environnement virtuel. Typiquement pour le serveur sous debian 9 (python 3.5), il faut passer par conda:

```
$ conda base
```

puis 

```
$ python3 VST.py
```

## À faire
la fonction G.node est dépréciée dans networkx 2.4. À priori le changement à faire serait simplement d'ajouter un *s*:
```
G.node[1]['name'] = 'alpha'
```
devient
```
G.nodes[1]['name'] = 'alpha'
```
