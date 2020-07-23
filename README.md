# Readme des traitements panoramas

## Mise en oeuvre.

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

## En cas de problème 

### avec les platines
1. s'assurer que les ports USB ont les bonnes permissions. Une possibilité est de les transférer au groupe *pimotor*
Si 
>$ ls -l /dev/ttyUSB*
crw-rw---- 1 root dialout 188, 0 juin   2 10:00 /dev/ttyUSB0
crw-rw---- 1 root dialout 188, 1 juin   2 09:59 /dev/ttyUSB1

Alors
>$ sudo chgrp pimotor /dev/ttyUSB*

et vérifier que 
```
ls -l /dev/ttyUSB*
crw-rw---- 1 root pimotor 188, 0 juin   2 10:00 /dev/ttyUSB0
crw-rw---- 1 root pimotor 188, 1 juin   2 09:59 /dev/ttyUSB1 
```

2. et de s'assurer que l'utilisateurs est bien dans le groupe pimotor
Ici, l'utilisateur *dyco* a été ajouté au groupe *pimotor* (attention la sortie de cette commande n'est à jour qu'après deconnexion / reconnexion)
> $ groups dyco
dyco : dyco adm cdrom sudo dip plugdev lpadmin sambashare manip pimotor 

3. Si erreur 
> pipython.pidevice.gcserror.GCSError: Unallowable move attempted on unreferenced axis, or move attempted with servo off (5)

vérifier que les controleurs sont *on* et référencées avec les commandes suivantes executées depuis *PI_terminal*:
> SVO 1 1

> FNL 1

> FPL 1

> MOV 1 1
 
