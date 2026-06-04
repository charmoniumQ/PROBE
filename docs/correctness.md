# Prove correctness of highest peers / lowest peers

My highest peers are either highest peers of my parent or something else.

If something else, they are not peers of my parent, and there is a path from my parent to them or from them to my parent.

There is not a path from them to my parent, because then they would not be peers of me (they would be my ancestor). Therefore, there is a path from my parent to them.

They are either direct descendants or distant descendants of my parent.

If they are direct descendants, they are my siblings.

If they are distant descendants, they are not my highest peer, as their parent would be higher than them, their parent would be on the path to my parent, and their parent would also be my peer.

Therefore, we topo sort the graph. At each node, we set the highest peers to the highest peers of all parents plus all siblings, removing those which are not actually peers. Peers of my parent can be my ancestor but not my descendent (else they would not be peers of my parent). Siblings can be ancestors or descendants (parent -> sibling, parent -> me, me -> sibling; alternatively, flip the direction of me -> sibling).

The sources (nodes with in-degree = 0) are peers of each other. If they were not, there would be a path, and the in-degree would not be 0.
