# Readme des traitements panoramas

## Mise en oeuvre.

Le traitement est passé sur python 3.8 et networkx 2.5 Si cette version n'est pas disponible, utiliser un environnement virtuel. Typiquement pour le serveur sous debian 9 (python 3.5), il faut passer par conda:

```
$ conda base
```

puis 

```
$ python3 VST.py
```

ou pour une image unique
```
$ python3 VS_one.py
```

Attention que les images soient bien binarisées et pas en niveau de gris.


## Modifs
### G.node
la fonction G.node est dépréciée dans networkx 2.4. fait est d'ajouter un *s*:
```
G.node[1]['name'] = 'alpha'
```
devient
```
G.nodes[1]['name'] = 'alpha'
```

### nx.connected_component_subgraphs
nx.connected_component_subgraphs deprecated in nx2.1 and removed from 2.4, replace by 
    (G.subgraph(c) for c in connected_components(G))
    Or (G.subgraph(c).copy() for c in connected_components(G))
    Gcc = sorted(nx.connected_component_subgraphs(G), key=len, reverse=True)


### Images_test/
contient des images pour faire des tests rapides

### C_net_functions/
contient les utilitaires pour compiler net_utilities.

## En cas de problème 

### avec les platines
1. s'assurer que les ports USB ont les bonnes permissions. Une possibilité est de les transférer au groupe *pimotor*
Si les ports ttyUSB* appartiennent au groupe dialout
```
$ ls -l /dev/ttyUSB*
crw-rw---- 1 root dialout 188, 0 juin   2 10:00 /dev/ttyUSB0
crw-rw---- 1 root dialout 188, 1 juin   2 09:59 /dev/ttyUSB1
```

Alors on peut changer pour le groupe pimotor avec:
```
>$ sudo chgrp pimotor /dev/ttyUSB*
```

On vérifie que les groupes ont bien changé:
```
ls -l /dev/ttyUSB*
crw-rw---- 1 root pimotor 188, 0 juin   2 10:00 /dev/ttyUSB0
crw-rw---- 1 root pimotor 188, 1 juin   2 09:59 /dev/ttyUSB1 
```

2. et de s'assurer que l'utilisateurs est bien dans le groupe pimotor
Ici, l'utilisateur *dyco* a été ajouté au groupe *pimotor* (attention la sortie de cette commande n'est à jour qu'après deconnexion / reconnexion)
``` 
$ groups dyco
dyco : dyco adm cdrom sudo dip plugdev lpadmin sambashare manip pimotor 
```

3. Si erreur 
```
pipython.pidevice.gcserror.GCSError: Unallowable move attempted on unreferenced axis, or move attempted with servo off (5)
```

vérifier que les controleurs sont *on* et référencées avec les commandes suivantes executées depuis *PI_terminal*:
```
SVO 1 1
FNL 1
FPL 1
MOV 1 1
``` 
