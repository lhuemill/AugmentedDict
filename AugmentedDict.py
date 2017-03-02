"""An augmented sorted mapping container.

Copyright 2017 Louis Huemiller

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

This module provides the implementation of a sorted mapping container, where
each entry also contains an additional augmented value.  Beyond the typical
dictionary methods, a method is also provided to efficiently find the
first entry where the sum of all the augmented values is less than or
equal to a specified value.

The initial implementation maintains the entries through the use of a
binary-search-tree.  Beyond a minimal implementation of a binary-search-tree,
this implementation also provides:

  + Semi-Balanced Tree
    A red-black tree is used, so that even in the worst case
    the distance to the lowest leaf is no more than two times
    the highest leaf.  Although the tree is typically not fully
    balanced, the cost of maintaining the semi-balanced tree is
    significantly lower than a fully-balanced tree.

  + Calculated Parent Pointer
    To save space, the nodes that comprise the binary-search-tree
    do not contain a direct reference to its parent node.  Instead,
    the location of a parent node is calculated on demand, usually by
    traversing down from the root node.

  + Augmented Value
    Beyond the key and value of each entry, each entry also maintains
    an augmented value, which must be > 0.0.  By default, each entry
    has an augmented value of one.  An efficient mechanism for finding
    the first entry where the sum of the augmented value of all earlier
    entries is less than or equal to a specified value is provided.

Classes:

    AugmentedDict

Basic Mapping Container Functions:

    adict = AugmentedDict()  # Create a new empty augmented dictionary.
    adict[key] = value       # Add or update value of entry specified by key.
    del adict[key]           # Remove entry specified by key.
    val = adict[key]         # Obtain value of entry for specified key.
    adict.keys()             # Iterator over keys.
    adict.values()           # Iterator over each entries value.
    adict.items()            # Iterator over each entries (key, value) tuple.

Sequential Access Functions:

    first()        # Return (key, value) tuple of entry with
                   # lowest key.
    last()         # Return (key, value) tuple of entry for
                   # highest key.
    next(key)      # Return (key, value) tuple of next entry
                   # after entry for specified key.
    prev(key)      # Return (key, value) tuple of previous entry
                   # before entry for specified key.

Augmented Value:
  Beyond the key and value of each entry, each entry also has an augmented
  value, which must be > 0.0.  By default, each entry has an augmented value
  of 1.  A non-default augmented value is provided by having the value
  portion of an entry extended with a method named augmented_val().  A
  default value of 1 is used when the value portion of an entry does not
  contain a function named augmented_value().  When all entries use the
  default augmented value of 1, aug_find(n) finds the entry at rank n.
  
  Augmented values of both integral and float types are supported.  An
  augmented dictionary may even have a mixture of augmented value types,
  where some entries have an integral augmented value and others have an
  augmented value of type float.  Note: when any of the augmented values are
  of type float, it is the responsibility of the caller on insertion of each
  new entry that the sum of the augmented values in any sequential subset of
  entries is < the sum of all those values plus the smallest augmented value
  of any entry.  In general it is best for all the entries to use either the
  default augmented value or an augmented value of type int.  Use of augmented
  values of type float is discouraged, in that it requires the caller to use a
  range of augmented values that assure the uniqueness of augmented ranges,
  even when rounding errors are possibly accumulated due to tree rebalance
  operations.

  Augmented Value Functions:

      aug_sum_before(key)  # Returns the sum of all the augmented values
                           # before the entry specified by key.
      aug_find(amount)     # Returns the (key, value) tuple of the first
                           # entry where the augmented sum of all entries
                           # before that entry is >= amount.  A ValueError
                           # is raised if amount is < 0 or >= the sum of
                           # the augmented values in all the entries.
"""

from __future__ import print_function

from enum import Enum

# Marker for a temporary diagnostic statement
def diag(): pass

class AugmentedDict(object):
    """
    AugmentedDict() -> new empty Augmented Dictionary.
    """

    def __init__(self):
        """AugmentedDict Constructor"""

        self._root = None

    def __str__(self):
        """d.__str__() <==> str(d)"""

        rv = 'AugmentedDict:\n'
        if self._root:
            rv += ('  _root:\n%s' % self._root.dump_subtree(self._root, 4))
        else:
            rv += '  _root: %s' % self._root

        return(rv)

    def __getitem__(self, key):
        """d.__getitem__(key) <==> d[key]

        Finds and returns the value of the entry specified by key.

        Raises:
            KeyError - Entry for the specified key does not exist.
        """

        node = self._root.find(key) if self._root else None
        if not node:
            raise KeyError('key of %s not found' % key)

        return node.val

    def __setitem__(self, key, val):
        """d.__setitem__(key, val) <==> d[key]=val

        Creates a new entry with the given key and value, when an
        entry with the given key doesn't already exist.  When an
        entry of the given key already exists, the value portion of
        that entry is updated with the value given by val.
        
        Raises:
            ValueError - Augmented value support is enabled and
                         the new value has an invalid augmented value
                         (e.g. augmented value <= 0).
        """

        red = AugmentedDict.__Node.NodeColor.red
        black = AugmentedDict.__Node.NodeColor.black

        # Does a node already exists for the given key?
        if self._root:
            node = self._root.find(key)
            if node:
                node.aug_amt = AugmentedDict._val_aug_amt(node.val)
                node.aug_total_adjust(self._root, -node.aug_amt)
                node.val = val
                node.aug_amt = AugmentedDict._val_aug_amt(node.val)
                node.aug_total_adjust(self._root,
                        AugmentedDict._val_aug_amt(node.val))
                node.aug_subtotal = node.aug_amt
                node.aug_subtotal += (node.left.aug_subtotal
                        if node.left else 0)
                node.aug_subtotal += (node.right.aug_subtotal
                        if node.right else 0)
                return

        # Create new node.
        node = AugmentedDict.__Node(key, val)
        node.aug_amt = AugmentedDict._val_aug_amt(node.val)
        node.aug_subtotal = node.aug_amt

        # Add node to the leaf location specified by its key.
        if not self._root:
            node.color = black
            self._root = node
            return
        else:
            parent = self._root
            while True:
                assert parent.key != key
                if key < parent.key:
                    if not parent.left:
                        break
                    else:
                        parent = parent.left
                else:
                    if not parent.right:
                        break
                    else:
                        parent = parent.right
            if key < parent.key:
                parent.left = node
            else:
                parent.right = node
            node.aug_total_adjust(self._root, node.aug_amt)

        node.color = red

        # As needed re-balance tree.
        while parent and parent.color == red:
            grandparent = node.grandparent(self._root)
            # A grandparent should exist, because there is a
            # red parent and at a minimum, there should be a
            # black root node above the parent.
            assert grandparent, ('Unexpected no grandparent')

            if parent is grandparent.left:
                uncle = grandparent.right
                if uncle and uncle.color == red:
                    # Case 1: Both parent and uncle are red.
                    assert parent.color == red
                    parent.color = black
                    uncle.color = black
                    grandparent.color = red
                    node = grandparent
                    parent = node.parent(self._root)
                else:
                    if node == parent.right:
                        node = parent
                        y = node.left_rotate()
                        parent = y
                        grandparent.left = y

                    parent.color = black
                    grandparent.color = red

                    tmp = grandparent.parent(self._root) 
                    y = grandparent.right_rotate()
                    if tmp:
                        if grandparent.key < tmp.key:
                            tmp.left = y
                        else:
                            tmp.right = y
                    else:
                        self._root = y
            else:
                uncle = grandparent.left
                if uncle and uncle.color == red:
                    # Case 1: Both parent and uncle are red.
                    assert parent.color == red
                    parent.color = black
                    uncle.color = black
                    grandparent.color = red
                    node = grandparent
                    parent = node.parent(self._root)
                else:
                    if node == parent.left:
                        node = parent
                        y = node.right_rotate()
                        parent = y
                        grandparent.right = y

                    parent.color = black
                    grandparent.color = red

                    tmp = grandparent.parent(self._root) 
                    y = grandparent.left_rotate()
                    if tmp:
                        if grandparent.key < tmp.key:
                            tmp.left = y
                        else:
                            tmp.right = y
                    else:
                        self._root = y

            parent = node.parent(self._root)
            if not parent or not parent.parent(self._root):
                break

        self._root.color = black

        return

    def __delitem__(self, key):
        """d.__delitem__(y) <==> del d[y]
        
        Deletes the entry with the specified key.

        Raises:
            KeyError - Entry for the specified key does not exist.
        """

        red = AugmentedDict.__Node.NodeColor.red
        black = AugmentedDict.__Node.NodeColor.black

        node = self._root.find(key)
        if not node:
            raise KeyError('key of %s not found' % key)

        if not node.left or not node.right:
            y = node
        else:
            y = node.prev(self._root)

        x = y.left if y.left else y.right

        y_parent = y.parent(self._root)
        x_parent = y_parent
        node.aug_total_adjust(self._root, -node.aug_amt)

        if not y_parent:
            self._root = x
        else:
            if y is y_parent.left:
                y_parent.left = x
            else:
                y_parent.right = x
            y_parent.aug_subtotal = y_parent.aug_amt
            y_parent.aug_subtotal += (y_parent.left.aug_subtotal
                    if y_parent.left else 0)
            y_parent.aug_subtotal += (y_parent.right.aug_subtotal
                    if y_parent.right else 0)

        if y is not node:
            node.key = y.key
            node.val = y.val
            if y_parent is not node:
                parents = y_parent.parents(self._root)
                while parents:
                    entry = parents.pop()
                    if entry is node:
                        break
                    entry.aug_subtotal -= y.aug_amt
            node.aug_amt = y.aug_amt
            node.aug_subtotal = node.aug_amt
            node.aug_subtotal += node.left.aug_subtotal if node.left else 0
            node.aug_subtotal += (node.right.aug_subtotal
                    if node.right else 0)
            y_parent.aug_subtotal = y_parent.aug_amt
            y_parent.aug_subtotal += (y_parent.left.aug_subtotal
                    if y_parent.left else 0)
            y_parent.aug_subtotal += (y_parent.right.aug_subtotal
                    if y_parent.right else 0)

        # If needed rebalance tree
        if y.color == black:
            while ((x is not self._root) and (x == None or x.color == black)):
                if x is x_parent.left:
                    w = x_parent.right

                    if w.color == red:
                        w.color = black
                        x_parent.color = red

                        tmp1 = x_parent.parent(self._root)
                        tmp2 = x_parent.left_rotate()
                        if tmp1:
                            if tmp1.key > tmp2.key:
                                tmp1.left = tmp2
                            else:
                                tmp1.right = tmp2
                        else:
                            self._root = tmp2

                        w = x_parent.right

                    if ((w.right == None or w.right.color == black)
                           and (w.left == None or w.left.color == black)):
                        w.color = red
                        x = x_parent
                        x_parent = x.parent(self._root)
                    else:
                        if w.right == None or w.right.color == black:
                            w.left.color = black
                            w.color = red
                            tmp1 = w.parent(self._root)
                            tmp2 = w.right_rotate()
                            if tmp1:
                                if tmp1.key > tmp2.key:
                                    tmp1.left = tmp2
                                else:
                                    tmp1.right = tmp2
                            else:
                                self._root = tmp2

                            w = x_parent.right

                        w.color = x_parent.color

                        x_parent.color = black

                        w.right.color = black

                        tmp1 = x_parent.parent(self._root)
                        tmp2 = x_parent.left_rotate()
                        if tmp1:
                            if tmp1.key > tmp2.key:
                                tmp1.left = tmp2
                            else:
                                tmp1.right = tmp2
                        else:
                            self._root = tmp2

                        x = self._root
                        x_parent = None
                else:
                    w = x_parent.left

                    if w.color == red:
                        w.color = black
                        x_parent.color = red

                        tmp1 = x_parent.parent(self._root)
                        tmp2 = x_parent.right_rotate()
                        if tmp1:
                            if tmp1.key > tmp2.key:
                                tmp1.left = tmp2
                            else:
                                tmp1.right = tmp2
                        else:
                            self._root = tmp2

                        w = x_parent.left

                    if ((w.right == None or w.right.color == black)
                            and (w.left == None or w.left.color == black)):
                        w.color = red
                        x = x_parent
                        x_parent = x.parent(self._root)
                    else:
                        if w.left == None or w.left.color == black:
                            w.right.color = black
                            w.color = red
                            tmp1 = w.parent(self._root)
                            tmp2 = w.left_rotate()
                            if tmp1:
                                if tmp1.key > tmp2.key:
                                    tmp1.left = tmp2
                                else:
                                    tmp1.right = tmp2
                            else:
                                self._root = tmp2

                            w = x_parent.left

                        w.color = x_parent.color

                        x_parent.color = black

                        w.left.color = black

                        tmp1 = x_parent.parent(self._root)
                        tmp2 = x_parent.right_rotate()
                        if tmp1:
                            if tmp1.key > tmp2.key:
                                tmp1.left = tmp2
                            else:
                                tmp1.right = tmp2
                        else:
                            self._root = tmp2

                        x = self._root
                        x_parent = None

            if x:
                x.color = black

        return

    def keys(self):
        """d.keys() -> list of d\'s keys
        
        Keys are provided in the order determined by the <
        operator of the entries keys.
        """

        if self._root == None:
            return

        current = self._root.leftmost()
        yield current.key

        current = current.next(self._root)
        while current != None:
            yield current.key
            current = current.next(self._root)

        return
    
    def values(self):
        """d.values() -> list of d\'s values
        
        Values are provided from entries in an an order that is
        determined by the < operator on the key portion of each entry.
        """

        if self._root == None:
            return

        current = self._root.leftmost()
        yield current.val

        current = current.next(self._root)
        while current != None:
            yield current.val
            current = current.next(self._root)

        return

    def items(self):
        """d.items() -> list of d\'s (key, value) tuples
        
        The (key, value) tuples are returned in an order that is determined
        by the < operator on the key portion of the entries.
        """

        if self._root == None:
            return

        current = self._root.leftmost()
        yield (current.key, current.val)

        current = current.next(self._root)
        while current != None:
            yield (current.key, current.val)
            current = current.next(self._root)

        return

    def find(self, key):
        """Find entry with specified key.  Returns corresponding
        (key, value) tuple of entry specified by key.
        
        Raises:
            KeyError - Entry for the specified key does not exist.
        """

        node = self._root.find(key)
        if not node:
            raise KeyError('key of %s not found' % key)

        return (node.key, node.val)

    def first(self):
        """Returns (key, val) tuple of first entry (entry with lowest key).

        Raises:
            RuntimeError - First entry does not exist, because the
                           dictionary is empty.
        """

        if not self._root:
            raise RuntimeError('Empty Dictionary')

        node = self._root
        while node.left:
            node = node.left

        return (node.key, node.val)

    def last(self):
        """Returns (key, val) tuple of last entry (entry with highest key).

        Raises:
            RuntimeError - Last entry does not exist, because the
                           dictionary is empty.
        """

        if not self._root:
            raise RuntimeError('Empty Dictionary')

        node = self._root
        while node.right:
            node = node.right

        return (node.key, node.val)

    def next(self, key):
        """
        Returns (key, val) tuple of next entry after the entry specified
        by key.

        Raises:
            KeyError - An entry for the specified key does not exist.
            RuntimeError - Next entry does not exist, because the entry
                           specified by key is currently the last entry.
        """

        node = self._root.find(key) if self._root else None
        if not node:
            raise KeyError('key of %s not found' % key)

        node = node.next(self._root)
        if node:
            return (node.key, node.val)
        else:
            raise RuntimeError('Key specifies last entry')

    def prev(self, key):
        """
        Returns (key, val) tuple of entry immediately before the
        entry specified by key.

        Raises:
            KeyError - An entry for the specified key does not exist.
            RuntimeError - Previous entry does not exist, because the entry
                           specified by key is currently the first entry.
        """

        node = self._root.find(key) if self._root else None
        if not node:
            raise KeyError('key of %s not found' % key)

        node = node.prev(self._root)
        if node:
            return (node.key, node.val)
        else:
            raise RuntimeError('Key specifies first entry')

    def aug_sum_before(self, key):
        """Returns sum of augmented values of all entries before the
        entry specified by key.

        Raises:
            KeyError - Entry for the specified key does not exist.
            RuntimeError - Support for augmented values is currently disabled.
        """
        
        node = self._root.find(key) if self._root else None
        if not node:
            raise KeyError('key of %s not found' % key)

        parents = node.parents(self._root)
        r = node.left.aug_subtotal if node.left else 0
        y = node
        while y:
            parent = parents.pop() if parents else None
            if parent and y == parent.right:
                r += (parent.left.aug_subtotal + parent.aug_amt
                    if parent.left else parent.aug_amt)
            y = parent

        return r

    def aug_find(self, amt):
        """Returns the (key, value) tuple of the first entry where
        the sum of the augmented values in all the entries before
        that entry is >= amt.

        Raises:
            RuntimeError - Support for augmented values is currently disabled.
            ValueError - amt is <= 0
            ValueError - amt is >= sum of augmented values of all the entries.
        """

        if amt < 0.0:
            raise ValueError('Invalid aug_find amount of: %s' % amt)

        node = self._root
        if not node:
            raise ValueError('All aug_find amount are invalid for an empty '
                    'dictionary')

        val = self._root.aug_find(amt)
        if val == (None, None):
            raise ValueError('Amount of %s >= sum of augmented values '
                    'of all entries.' % amount)
        return val

    def diag_validate(self, diag_str=''):
        """Validates the overall state of the augmented dictionary.
        Although an error should never be found, when an error is
        detected an assertion failure is produced with a string
        describing the error, plus the contents of diag_str.  Callers
        typically either use the default empty diag_str or provide
        a diag_str whose contents may be useful in determining the
        sequence that got the augmented dictionary into an invalid state.
        """

        # Nothing to validate when there are no nodes.
        if not self._root:
            return

        # Use passed in diagnostic string or create one from scratch.
        # This string is only used by error messages.
        if len(diag_str):
            diag_str = '\n' + diag_str.rstrip() + '\n'
        else:
            diag_str += 'actual:\n'
            diag_str += AugmentedDict._str_indent(str(self), 2)

        # Validate root node is colored black.
        assert self._root.color == AugmentedDict.__Node.NodeColor.black, (
                'Unexpected root node color\n'
                '  root_node_color: %s\n'
                '  expected: %s\n'
                '  %s'
                % (self._root.color, AugmentedDict.__Node.NodeColor.black,
                    diag_str))

        # Recursively validate each of the nodes.
        self.__node_validate(self._root, diag_str)

        # Validate black height is consistent from the root node.
        # If consistent from root node, then it is also consistent
        # in all subtrees.
        black_height = self._root.black_height()
        assert black_height != None, (
                'Inconsistent black height\n'
                ' %s' % diag_str)

    # -------- Implementation Private --------
    @staticmethod
    def _val_aug_amt(val):
        if hasattr(val, 'augmented_val'):
            return val.augmented_val()
        else:
            return 1

    @staticmethod
    def _str_indent(s, indent):
        return('%s%s' % (' ' * indent, s.replace('\n', '\n' + ' ' * indent)))

    class __Node:
        class NodeColor(Enum):
            red = 0
            black = 1

        def __init__(self, key, val):
            self.key = key
            self.val = val
            self.left = None
            self.right = None
            self.color = None

        def __str__(self):
            rv = 'id: %#x\n' % id(self)
            rv += 'key: %s val: %s\n' % (
                    (self.key.__str__(), self.val.__str__()))
            rv += 'color: %s\n' % self.color
            if hasattr(self, 'aug_amt'):
                rv += 'aug_amt: %s\n' % self.aug_amt
            if hasattr(self, 'aug_subtotal'):
                rv += 'aug_subtotal: %s\n' % self.aug_subtotal
            rv += 'left: %s\n' % (hex(id(self.left))
                    if self.left else self.left)
            rv += 'right: %s' % (hex(id(self.right))
                    if self.right else self.right)
            return rv

        # @staticmethod
        # def val_aug_amt(val):
        #     if hasattr(val, 'augmented_val'):
        #         return val.augmented_val()
        #     else:
        #         return 1

        def parent(self, root):
            if self is root:
                return None

            parent = root
            while True:
                if self.key < parent.key:
                    assert parent.left != None
                    if parent.left.key == self.key:
                        return parent
                    parent = parent.left
                else:
                    assert parent.right != None
                    if (parent.right.key == self.key):
                        return parent
                    parent = parent.right

        def parents(self, root):
            assert root != None

            rv = []

            parent = root
            while parent.key != self.key:
                if (self.key < parent.key):
                    assert parent.left != None
                    rv.append(parent)
                    parent = parent.left
                else:
                    assert parent.right != None
                    rv.append(parent)
                    parent = parent.right

            return rv

        def grandparent(self, root):
            parent = self.parent(root)
            if parent == None:
                return None

            return parent.parent(root)

        def leftmost(self):
            node = self
            while (node.left):
                node = node.left
            return node

        def last(self):
            node = self
            while (node.right):
                node = node.right
            return node

        def next(self, root):
            node = self

            if node.right:
                node = node.right
                if node.left:
                    node = node.leftmost()
            else:
                parents = node.parents(root)
                while parents:
                    parent = parents.pop()
                    if parent.left is node:
                        node = parent
                        break
                    node = parent
                else:
                    node = None

            return node

        def prev(self, root):
            node = self

            if node.left:
                node = node.left
                if node.right:
                    node = node.last()
            else:
                parents = node.parents(root)
                while parents:
                    parent = parents.pop()
                    if parent.right is node:
                        node = parent
                        break
                    node = parent
                else:
                    node = None

            return node

        def find(self, key):
            node = self
            while node:
                if (node.key == key):
                    return node
                if (key < node.key):
                    node = node.left
                else:
                    node = node.right
            return None

        def aug_sum_before(self, root):
            total = (self.aug_subtotal
                    - (self.right.aug_subtotal if self.right else 0))
            parents = self.parents(root)
            prev_parent = self
            while parents:
                parent = parents.pop()
                if parent.right is prev_parent:
                    total += parent.aug_subtotal - prev_parent.aug_subtotal
                prev_parent = parent
            return total

        def aug_recalculate(self):
            self.aug_amt = AugmentedDict._val_aug_amt(self.val)

            if self.left:
                self.left.aug_recalculate()

            if self.right:
                self.right.aug_recalculate()

            self.aug_subtotal = self.aug_amt
            self.aug_subtotal += self.left.aug_subtotal if self.left else 0
            self.aug_subtotal += self.right.aug_subtotal if self.right else 0

        def aug_delete_info(self):
            if self.left:
                self.left.aug_delete_info()
            if self.right:
                self.right.aug_delete_info()


        #        +----+                                +---+       
        #        |self|                                | y |            
        #        +----+                                +---+         
        #       /      \                              /     \             
        #      /        \           ---->            /       \            
        #     a          +---+                 +----+         c              
        #                | y |                 |self|                 
        #                +---+                 +----+                 
        #               /     \               /      \                
        #              /       \             /        \               
        #             b         c           a          b              
        #
        # Returns: y
        #                                                             
        def left_rotate(self):
            y = self.right
            self.right = y.left
            y.left = self
            if hasattr(y, 'aug_amt'):
                self.aug_subtotal = self.aug_amt
                self.aug_subtotal += (self.left.aug_subtotal
                        if self.left else 0)
                self.aug_subtotal += (self.right.aug_subtotal
                        if self.right else 0)
                y.aug_subtotal = y.aug_amt
                y.aug_subtotal += y.left.aug_subtotal if y.left else 0
                y.aug_subtotal += y.right.aug_subtotal if y.right else 0

            return y

        #              +----+                  +---+
        #              |self|                  | y |
        #              +----+                  +---+
        #             /      \                /     \                      
        #            /        \    ---->     /       \                     
        #       +---+          c            a         +----+                  
        #       | y |                                 |self|          
        #       +---+                                 +----+          
        #      /     \                               /      \         
        #     /       \                             /        \        
        #    a         b                           b          c       
        #
        # Returns: y
        #                                                             
        def right_rotate(self):
            y = self.left
            self.left = y.right
            y.right = self
            if hasattr(self, 'aug_amt'):
                self.aug_subtotal = self.aug_amt
                self.aug_subtotal += (self.left.aug_subtotal
                        if self.left else 0)
                self.aug_subtotal += (self.right.aug_subtotal
                        if self.right else 0)
                y.aug_subtotal = y.aug_amt
                y.aug_subtotal += y.left.aug_subtotal if y.left else 0
                y.aug_subtotal += y.right.aug_subtotal if y.right else 0

            return y

        def aug_total_adjust(self, root, amt):
            node = self
            initial_aug_total = node.aug_sum_before(root)
            prev = node.prev(root)
            prev_node_aug_total = prev.aug_sum_before(root) if prev else 0
            assert -amt <= (initial_aug_total - prev_node_aug_total), (
                    'amt: %s prev_node_aug_total: %s initial_aug_total: %s'
                % (amt, prev_node_aug_total, initial_aug_total))
            parents = self.parents(root)
            while parents:
                parent = parents.pop()
                parent.aug_subtotal += amt
                node = parent

        def aug_find(self, amt):
            r = self.left.aug_subtotal if self.left else 0
            if (amt >= r) and (amt < r + self.aug_amt):
                return (self.key, self.val)
            elif amt < r:
                return self.left.aug_find(amt)
            else:
                return (self.right.aug_find(amt - (r + self.aug_amt))
                        if self.right else (None, None))

        def black_height(self):
            red = self.NodeColor.red
            black = self.NodeColor.black

            # If both children are leaves return 1, becauses leaves are
            # always considered black, plus 1 more if node is also black.
            if self.left == None and self.right == None:
                return 1 + (1 if self.color == black else 0)

            black_height_left = (self.left.black_height()
                    if self.left else 1)
            black_height_right = (self.right.black_height()
                    if self.right else 1)

            # Return None if left and right black heights are not
            # the same, as an indication of inconsistent black
            # height from this node.
            if black_height_left != black_height_right:
                return None

            # Return black height of either child plus 1 more if this
            # node is also black.
            return black_height_left + (1 if self.color == black else 0)

        def dump_subtree(self, root, indent):
            node = self
            prefix = ' ' * indent
            rv = '%s%s\n' % (prefix, node.__str__().replace('\n', '\n'
                + prefix))

            parent = node.parent(root)
            if parent:
                rv += '%sparent: %#x\n' % (prefix, id(parent))
            else:
                rv += '%sparent: %s\n' % (prefix, parent)

            if node.left:
                rv += '%sleft:\n%s\n' % (prefix,
                    node.left.dump_subtree(root, indent + 2))
            else:
                rv += '%sleft: %s\n' % (prefix, node.left)

            if node.right:
                rv += '%sright:\n%s\n' % (prefix,
                    node.right.dump_subtree(root, indent + 2))
            else:
                rv += '%sright: %s\n' % (prefix, node.right)

            rv = rv.rstrip()
            return rv

    def __node_validate(self, node, diag_str):
        red = AugmentedDict.__Node.NodeColor.red
        black = AugmentedDict.__Node.NodeColor.black

        if node.color == red:
            if node.left:
                assert node.left.color == black, (
                        'node.key: %s node.color: %s\n'
                        'node.left.key: %s node.left.color: %s\n'
                        '%s'
                        % (node.key, node.color, node.left.key,
                            node.left.color, diag_str))
            if node.right:
                assert node.right.color == black, (
                        'node.key: %s node.color: %s\n'
                        'node.right.key: %s node.right.color: %s\n'
                        '%s'
                        % (node.key, node.color, node.right.key,
                            node.right.color, diag_str))

        if node.left:
            assert node.left.key < node.key, ('node.key: %s\n%s'
                    % (node.key, diag_str))
            self.__node_validate(node.left, diag_str)

        if node.right:
            assert node.key < node.right.key, ('node.key: %s\n%s'
                % (node.key, diag_str))
            self.__node_validate(node.right, diag_str)


# -------- Tests --------
if __name__ == '__main__':

    import itertools
    import math
    import numbers
    import numpy
    import random
    import string
    import sys
    import time
    import unittest
    from collections import namedtuple

    # Make assertRaisesRegex available in Python versions 2.7 through 3.1
    # by renaming assertRaisesRegex to assertRaisesRegexp.
    assert bool(sys.version_info.major > 2
            or ((sys.version_info.major == 2)
                and (sys.version_info.minor >= 7))), (
            'Need at least Python version 2.7, which introduced\n'
            'unittest.TestCase.assertRaisesRegexp\n'
            'sys.version_info.major: %s sys.version_info.minor: %s'
            % (sys.version_info.major, sys.version_info.minor))
    if ((sys.version_info.major < 3)
            or (sys.version_info.major == 3 and sys.version_info.minor <= 1)):
        unittest.TestCase.assertRaisesRegex = (
                unittest.TestCase.assertRaisesRegexp)


    class TestSupport(object):
        # Type that describes a single expected value.
        ExpectedEntry = namedtuple('EpectedEntry', 'key val aug_amt')

        # Extended integral and float types, with an augmented value
        # determined from the subclass value.  These types are mostly
        # used in various tests to create a value with a non-default
        # augmented amount.  For example, AugIntMod100(1234) creates
        # an integral value of 1234 and an augmented amount of 34.
        class AugIntDiv10(int):
            def augmented_val(self):
                return int(self / 10 if self / 10 != 0 else 3)

        class AugIntMod100(int):
            def augmented_val(self):
                if self >= 0:
                    return int(self % 100 if self % 100 != 0 else 12)
                else:
                    return int(-self % 100 if -self % 100 != 0 else 12)

        class AugFloatDiv100(float):
            def augmented_val(self):
                return float(self / 100 if self / 100 > 0.0 else 12.34)

        @staticmethod
        def expected_key_aug_start(key, expected):
            expected_start = 0
            for entry in expected:
                if entry.key < key:
                    expected_start += entry.aug_amt
            return expected_start

        @staticmethod
        def expected_aug_total(expected):
            aug_total = 0
            for entry in expected:
                aug_total += entry.aug_amt
            return aug_total

        @staticmethod
        def check_expected(actual, expected, diag_str=''):
            # Produce a diagnostic string to be printed in cases
            # where an unexpected condition is detected.
            if len(diag_str):
                diag_str = '\n' + diag_str.rstrip() + '\n'
            diag_str += 'expected:\n'
            for entry in expected:
                diag_str += ('  key: %s val: %s aug_amt: %s aug_start: %s\n'
                        % (entry.key, entry.val, entry.aug_amt,
                            TestSupport.expected_key_aug_start(
                                entry.key, expected)))
            aug_total = TestSupport.expected_aug_total(expected)
            diag_str += 'aug_total: %s\n' % aug_total
            diag_str += 'actual:\n'
            diag_str += AugmentedDict._str_indent(actual.__str__(), 2)

            # Validate internal state is valid.
            actual.diag_validate(diag_str)

            # Check that actual correctly contains each of the
            # expected entries.
            for entry in expected:
                key, val = actual.find(entry.key)
                assert key == entry.key, ('Unexpected key of: %s\n'
                        'expected key of: %s\n%s' % (key, entry.key, diag_str))
                assert val == entry.val, ('Unexpected val of: %s for key: %s\n'
                        'expected val of: %s\n%s'
                        % (val, entry.key, entry.val, diag_str))
                aug_start = actual.aug_sum_before(entry.key)
                expected_aug_start = TestSupport.expected_key_aug_start(
                        entry.key, expected)
                if isinstance(expected_aug_start, numbers.Integral):
                    assert aug_start == expected_aug_start, (
                            'Unexpected aug_start of: %s for key: %s\n'
                            'expected aug_start of: %s\n%s'
                            % (aug_start, entry.key, expected_aug_start,
                                diag_str))
                else:
                    assert numpy.isclose(aug_start, expected_aug_start), (
                            'Unexpected aug_start of: %s for key: %s\n'
                            'expected aug_start of: %s\n%s'
                            % (aug_start, entry.key, expected_aug_start,
                                diag_str))

            # Validate that expected key is at each aug value
            expected_sorted_keys = sorted([entry.key for entry in expected])
            if isinstance(aug_total, numbers.Integral):
                # All augmented values are integral
                expected_aug_start = 0
                for expected_key in expected_sorted_keys:
                    expected_entry = [val for val in expected if
                            val.key == expected_key][0]

                    # Validate key obtained at start of range.
                    aug_try = expected_aug_start
                    key = actual.aug_find(aug_try)[0]
                    assert key == expected_key, ('Unexpected key of: %s '
                            'at aug_try: %s\n'
                            'expected key of: %s\n%s'
                            % (key, aug_try, expected_key, diag_str))

                    # Validate key obtained at aug_start + 1.
                    if expected_entry.aug_amt >= 2:
                        aug_try = expected_aug_start + 1
                        key = actual.aug_find(aug_try)[0]
                        assert key == expected_key, ('Unexpected key of: '
                                '%s at aug_try: %s\n'
                                'expected key of: %s\n%s'
                                % (key, aug_try, expected_key, diag_str))

                    # Validate key obtained at aug_end.
                    if expected_entry.aug_amt >= 3:
                        aug_try = (expected_aug_start
                                + expected_entry.aug_amt - 1)
                        key = actual.aug_find(aug_try)[0]
                        assert key == expected_key, ('Unexpected key of: '
                                '%s at aug_try: %s\n'
                                'expected key of: %s\n%s'
                                % (key, aug_try, expected_key, diag_str))

                    expected_aug_start += expected_entry.aug_amt
            else:
                # One or more augmented values are of type float
                previous_key = None
                expected_aug_start = 0.0
                for expected_key in expected_sorted_keys:
                    expected_entry = [val for val in expected if
                            val.key == expected_key][0]

                    # Validate key obtained at start of range.
                    # Due to floating point rounding, key from previous
                    # entry is also valid.
                    aug_try = expected_aug_start
                    key = actual.aug_find(aug_try)[0]
                    expected_keys = [expected_key]
                    if previous_key != None:
                        expected_keys.append(previous_key)
                    assert key in expected_keys, (
                            'Unexpected key of: %s '
                            'at aug_try: %s\n'
                            'expected key of: %s\n%s'
                            % (key, aug_try, expected_keys, diag_str))

                    # Validate key obtained at 10% of range.
                    aug_try = (expected_aug_start
                            + expected_entry.aug_amt * 0.1)
                    key = actual.aug_find(aug_try)[0]
                    assert key == expected_key, (
                            'Unexpected key of: %s '
                            'at aug_try: %s\n'
                            'expected key of: %s\n%s'
                            % (key, aug_try, expected_key, diag_str))

                    previous_key = expected_key
                    expected_aug_start += float(expected_entry.aug_amt)

            # Validate results of first, last, next, and prev.
            expected_sorted_keys = sorted([entry.key for entry in expected])

            expected_key = (expected_sorted_keys[0]
                    if len(expected_sorted_keys) > 0 else None)
            try:
                (key, val) = actual.first()
            except RuntimeError:
                key = None
            assert key == expected_key, ('Unexpected first key\n'
                    'key: %s expected_key: %s\n%s'
                    % (key, expected_key, diag_str))

            expected_key = (expected_sorted_keys[-1:][0]
                    if len(expected_sorted_keys) > 0 else None)
            try:
                (key, val) = actual.last()
            except RuntimeError:
                key = None
            assert key == expected_key, ('Unexpected last key\n'
                    'key: %s expected_key: %s\n%s'
                    % (key, expected_key, diag_str))

            for i in range(len(expected_sorted_keys)):
                expected_next = (expected_sorted_keys[i + 1] if
                        i < (len(expected_sorted_keys) - 1) else None)
                try:
                    key_next = actual.next(expected_sorted_keys[i])[0]
                except RuntimeError:
                    key_next = None
                assert key_next == expected_next, ('Unexpected next key\n'
                        'i: %s expected_sorted_keys[i]: %s\n'
                        'key_next: %s\n'
                        'expected_next: %s\n'
                        '%s'
                        % (i, expected_sorted_keys[i], key_next, expected_next,
                            diag_str))

                expected_prev = (expected_sorted_keys[i - 1] if
                        i > 0 else None)
                try:
                    key_prev = actual.prev(expected_sorted_keys[i])[0]
                except RuntimeError:
                    key_prev = None
                assert key_prev == expected_prev, ('Unexpected prev key\n'
                        'i: %s expected_sorted_keys[i]: %s\n'
                        'key_prev: %s\n'
                        'expected_prev: %s\n'
                        '%s'
                        % (i, expected_sorted_keys[i], key_prev, expected_prev,
                            diag_str))

            # Validate AugmentedDict.keys(), AugmentedDict.values(),
            # and AugmentedDict.items()
            expected_dict = {x.key: x.val for x in expected}
            expected_keys = expected_sorted_keys
            expected_values = [expected_dict[x] for x in expected_keys]
            expected_items = [(x, expected_dict[x]) for x in expected_keys]

            keys_list = list(actual.keys())
            assert keys_list == expected_keys, ('Unexpected result from '
                    'actual.keys()\n'
                    '  actual.keys(): %s\n'
                    '  expected_keys: %s\n'
                    '  %s' % (keys_list, expected_keys, diag_str))

            values_list = list(actual.values())
            assert values_list == expected_values, ('Unexpected result from '
                    'actual.values()\n'
                    '  actual.values(): %s\n'
                    '  expected_values: %s\n'
                    '  %s' % (values_list, expected_values, diag_str))

            items_list = list(actual.items())
            assert items_list == expected_items, ('Unexpected result from '
                    'actual.items()\n'
                    '  actual.items(): %s\n'
                    '  expected_items: %s\n'
                    '  %s' % (items_list, expected_items, diag_str))

        @staticmethod
        def create_test_tree(num_nodes, seed = 0):
            node_creation_order = [
                    'node008_',
                    'node004_l',
                    'node012_r',
                    'node002_ll',
                    'node006_lr',
                    'node010_rl',
                    'node014_rr',
                    'node001_lll',
                    'node003_llr',
                    'node005_lrl',
                    'node007_lrr',
                    'node009_rll',
                    'node011_rlr',
                    'node013_rrl',
                    'node015_rrr',
                ]

            assert num_nodes <= len(node_creation_order), (
                    'num_nodes: %s max_supported: %s'
                    % (num_nodes, len(node_creation_order)))
            tree = AugmentedDict()
            expected = []
            random.seed(seed)

            for i, node_name in enumerate(node_creation_order):
                if i >= num_nodes:
                    break

                val = TestSupport.AugIntMod100(random.randint(0, 1000000))
                tree[node_name] = val
                expected_entry = TestSupport.ExpectedEntry(node_name, val,
                        val.augmented_val()) 
                expected.append(expected_entry)

            return tree, expected

        @staticmethod
        def perform_npairs_add(num_elements, num_add):
            if num_add > num_elements:
                raise ValueError('Num add > Num elements,\n'
                        '  num_elements: %s num_add: %s'
                        % (num_elements, num_add))

            # Create list of elements that key and value for each of the
            # adds will be taken from.
            elements = []
            for i in range(num_elements):
                elements.append(('key%03i' % i,
                    TestSupport.AugIntMod100(1234 + i)))

            for p in itertools.permutations(range(num_elements), num_add):
                tree = AugmentedDict()
                expected = []

                for j in p:
                    key = elements[j][0]
                    val = elements[j][1]
                    diag_str = ('permutation: %s\n'
                            'add key: %s val: %s aug_amt: %s'
                            % (p, key, val, val.augmented_val()))
                    tree[key] = val
                    expected.append(TestSupport.ExpectedEntry(key, val,
                        val.augmented_val()))
                    TestSupport.check_expected(tree, expected, diag_str)

        @staticmethod
        def perform_npairs_del(tree_size, num_del):
                for p in itertools.permutations(range(tree_size), num_del):
                    tree, orig_expected = TestSupport.create_test_tree(
                            tree_size)
                    expected = orig_expected

                    for j in p:
                        if j < 0 or j > tree_size:
                            raise ValueError('Invalid index j: %s for\n'
                                    '  tree_size: %s'
                                    % (j, tree_size))

                        # Delete from the tree and the expected list
                        # the jth element in the original tree.
                        diag_str = ('permutation: %s\n'
                                'delete: %s' % (p, j))
                        element_key = orig_expected[j].key
                        del tree[element_key]
                        expected = [x for x in expected if x.key != element_key]
                        TestSupport.check_expected(tree, expected, diag_str)

    # ---- Unit Tests ----
    class UnitTests(unittest.TestCase, TestSupport):
        # Maintain a list that provides the preferred order of test
        # execution.  Although this list is not used by the UnitTests
        # class and it should be possible to execute the unit tests in
        # any order, this list is used by other test suites to execute
        # these tests in the specified order.  Although the order is
        # arbitrary, it is mostly specified such that the simpler
        # tests are specified earlier in the list.
        preferred_execution_order = []

        # Test empty augmented binary search tree.
        preferred_execution_order.append('test_empty')
        def test_empty(self):
            tree = AugmentedDict()
            TestSupport.check_expected(tree, ( ))

            # Validate KeyError for non-existent key
            with self.assertRaisesRegex(KeyError, r'key of boat not found'):
                val = tree['boat']

        # Test augmented binary search tree with a single entry.
        preferred_execution_order.append('test_single_entry')
        def test_single_entry(self):
            tree = AugmentedDict()
            tree[1653] = 35
            TestSupport.check_expected(tree, (
                self.ExpectedEntry(1653, 35, 1), ))

            # Validate KeyError for non-existent key
            with self.assertRaisesRegex(KeyError, r'key of 5 not found'):
                val = tree[5]

        # Test string as key
        preferred_execution_order.append('test_key_str')
        def test_key_str(self):
            tree = AugmentedDict()
            tree['boat'] = 6592
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('boat', 6592, 1), ))

        # Test string as key and value
        preferred_execution_order.append('test_key_val_str')
        def test_key_val_str(self):
            tree = AugmentedDict()
            tree['car'] = 'blue'
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('car', 'blue', 1), ))

        # Test left child
        preferred_execution_order.append('test_left_child')
        def test_left_child(self):
            tree = AugmentedDict()
            tree['house'] = self.AugIntDiv10(52)  # Root node
            tree['car'] = self.AugIntDiv10(78)    # Left child of root node
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('house', 52, 5),
                self.ExpectedEntry('car', 78, 7),
            ))

        # Test right child
        preferred_execution_order.append('test_right_child')
        def test_right_child(self):
            tree = AugmentedDict()
            tree['berry'] = self.AugIntMod100(745)  # Root node
            tree['car'] = self.AugIntMod100(3548)   # Right child of root node
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('berry', 745, 45),
                self.ExpectedEntry('car', 3548, 48),
            ))

        # Test 3 nodes balanced - root with two children
        preferred_execution_order.append('test_three_nodes_balanced')
        def test_three_nodes_balanced(self):
            tree = AugmentedDict()
            tree['green'] = self.AugIntMod100(8830)  # Root node
            tree['blue'] = self.AugIntMod100(4812)   # Left child of root node
            tree['red'] = self.AugIntMod100(382)     # right child of root node
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('blue', 4812, 12),
                self.ExpectedEntry('green', 8830, 30),
                self.ExpectedEntry('red', 382, 82),
            ))

        # Test Left Rotate
        #
        # Addition of node with key of 'tree' initially creates the
        # following binary search tree:
        #
        #     'flower'
        #            \
        #             'rock'
        #                  \
        #                   'tree'
        #
        # A left rotate is used to change this to:
        #
        #                'rock'
        #                /    \
        #         'flower'    'tree'
        #
        preferred_execution_order.append('test_three_nodes_left_rotate')
        def test_three_nodes_left_rotate(self):
            tree = AugmentedDict()
            tree['flower'] = self.AugIntDiv10(6234)
            tree['rock'] = self.AugIntDiv10(5921)
            tree['tree'] = self.AugIntDiv10(9123)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('flower', 6234, 623),
                self.ExpectedEntry('rock', 5921, 592),
                self.ExpectedEntry('tree', 9123, 912),
            ))

        # Test Right Rotate
        #
        # Addition of node with key of 'tree' initially creates the
        # following binary search tree:
        #
        #              'jack'
        #              /
        #        'block'
        #        /
        #    'ball'
        #
        # A right rotate is used to change this to:
        #
        #                'block'
        #                /    \
        #           'ball'    'jack'
        #
        preferred_execution_order.append('test_three_nodes_right_rotate')
        def test_three_nodes_right_rotate(self):
            tree = AugmentedDict()
            tree['jack'] = self.AugIntMod100(2984)
            tree['block'] = self.AugIntMod100(1523)
            tree['ball'] = self.AugIntMod100(5421)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('ball', 5421, 21),
                self.ExpectedEntry('block', 1523, 23),
                self.ExpectedEntry('jack', 2984, 84),
            ))

        # Test add 4 nodes
        # A set of 4 tests, each that starts out with
        # the creation of the following tree:
        #
        #                  'node004_root'
        #                  /            \
        #     'node002_left'            'node006_right'
        #
        # Each of the 4 tests then add one of the following elements,
        # which will each get added to one of the 4 empty left or
        # right links of the initial 2 leaf nodes:
        #
        #   'node001_left_left'   # Added to left  of 'node002_left'
        #   'node003_left_right'  # Added to right of 'node002_left'
        #   'node005_right_left'  # Added to left  of 'node006_right'
        #   'node007_right_right' # Added to right of 'node006_right'
        #
        preferred_execution_order.append('test_add_four_nodes001')
        def test_add_four_nodes001(self):
            tree = AugmentedDict()
            tree['node004_root'] = self.AugIntMod100(6582)
            tree['node002_left'] = self.AugIntMod100(8723)
            tree['node006_right'] = self.AugIntMod100(8938)
            tree['node001_left_left'] = self.AugIntMod100(783)

            TestSupport.check_expected(tree, (
                self.ExpectedEntry('node004_root', 6582, 82),
                self.ExpectedEntry('node002_left', 8723, 23),
                self.ExpectedEntry('node006_right', 8938, 38),
                self.ExpectedEntry('node001_left_left', 783, 83),
            ))

        preferred_execution_order.append('test_add_four_nodes002')
        def test_add_four_nodes002(self):
            tree = AugmentedDict()
            tree['node004_root'] = self.AugIntMod100(6582)
            tree['node002_left'] = self.AugIntMod100(8723)
            tree['node006_right'] = self.AugIntMod100(8938)
            tree['node003_left_right'] = self.AugIntMod100(386)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('node004_root', 6582, 82),
                self.ExpectedEntry('node002_left', 8723, 23),
                self.ExpectedEntry('node006_right', 8938, 38),
                self.ExpectedEntry('node003_left_right', 386, 86),
            ))

        preferred_execution_order.append('test_add_four_nodes003')
        def test_add_four_nodes003(self):
            tree = AugmentedDict()
            tree['node004_root'] = self.AugIntMod100(6582)
            tree['node002_left'] = self.AugIntMod100(8723)
            tree['node006_right'] = self.AugIntMod100(8938)
            tree['node005_right_left'] = self.AugIntMod100(821)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('node004_root', 6582, 82),
                self.ExpectedEntry('node002_left', 8723, 23),
                self.ExpectedEntry('node006_right', 8938, 38),
                self.ExpectedEntry('node005_right_left', 821, 21),
            ))

        preferred_execution_order.append('test_add_four_nodes004')
        def test_add_four_nodes004(self):
            tree = AugmentedDict()
            tree['node004_root'] = self.AugIntMod100(6582)
            tree['node002_left'] = self.AugIntMod100(8723)
            tree['node006_right'] = self.AugIntMod100(8938)
            tree['node007_right_right'] = self.AugIntMod100(275)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('node004_root', 6582, 82),
                self.ExpectedEntry('node002_left', 8723, 23),
                self.ExpectedEntry('node006_right', 8938, 38),
                self.ExpectedEntry('node007_right_right', 275, 75),
            ))

        # Test add tree size == 5, npairs == 5
        #
        # For all permutations, of 5 elements from a tree size of
        # 5 elements (5! == 120 permutations), creates a tree
        # of 5 elements and then removes the 5 elements in the
        # order specified by the permutation.
        preferred_execution_order.append('test_add_tree5_npairs5')
        def test_add_tree5_npairs5(self):
            TestSupport.perform_npairs_add(5, 5)

        # Test Mixed Types
        #
        # Validates a tree where not all of the element values
        # are of the same type.
        preferred_execution_order.append('test_val_mixed_types')
        def test_val_mixed_types(self):
            tree = AugmentedDict()
            tree['Marigold'] = 6582
            tree['Lily'] = self.AugIntMod100(6458)
            tree['Poinsettia'] = 65.23
            tree['Daisy'] = self.AugIntDiv10(63487)
            tree['Violet'] = 'Blue'
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Marigold', 6582, 1),
                self.ExpectedEntry('Lily', 6458, 58),
                self.ExpectedEntry('Poinsettia', 65.23, 1),
                self.ExpectedEntry('Daisy', 63487, 6348),
                self.ExpectedEntry('Violet', 'Blue', 1),
            ))

        # Test Augmented Float
        #
        # Basic tree with entries that have augmented values of
        # type float.
        preferred_execution_order.append('test_augmented_float')
        def test_augmented_float(self):
            tree = AugmentedDict()
            tree['dog'] = self.AugFloatDiv100(753.926)
            tree['cat'] = self.AugFloatDiv100(2.383)
            tree['fish'] = self.AugFloatDiv100(1842.74)
            tree['goat'] = self.AugFloatDiv100(83.832)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('dog', 753.926, 7.53926),
                self.ExpectedEntry('cat', 2.383, 0.02383),
                self.ExpectedEntry('fish', 1842.74, 18.4274),
                self.ExpectedEntry('goat', 83.832, 0.83832),
            ))

        # Test Augmented Float and Int
        #
        # Basic tree with entries that have augmented values of
        # type float and int.
        preferred_execution_order.append('test_augmented_float_and_int')
        def test_augmented_float_and_int(self):
            tree = AugmentedDict()
            tree['Blue'] = self.AugIntMod100(753)
            tree['Green'] = self.AugFloatDiv100(3.482)
            tree['Brown'] = self.AugIntDiv10(803)
            tree['Yellow'] = self.AugFloatDiv100(2830.83)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Blue', 753, 53),
                self.ExpectedEntry('Green', 3.482, 0.03482),
                self.ExpectedEntry('Brown', 803, 80),
                self.ExpectedEntry('Yellow', 2830.83, 28.3083),
            ))

        # Test Replace Existing
        #
        # Creates a 5 node tree and then 1-by-1 changes the value
        # of each node and validates the contents of the entire
        # tree.
        preferred_execution_order.append('test_replace_existing')
        def test_replace_existing(self):
            tree = AugmentedDict()
            tree['Kazoo'] = self.AugIntMod100(3417)
            tree['Balloon'] = self.AugIntMod100(2512)
            tree['Tiddlywinks'] = self.AugIntMod100(8412)
            tree['Boat'] = self.AugIntMod100(3712)
            tree['Top'] = self.AugIntMod100(8732)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Balloon', 2512, 12),
                self.ExpectedEntry('Boat', 3712, 12),
                self.ExpectedEntry('Kazoo', 3417, 17),
                self.ExpectedEntry('Tiddlywinks', 8412, 12),
                self.ExpectedEntry('Top', 8732, 32),
            ))

            tree['Top'] = self.AugIntMod100(523)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Balloon', 2512, 12),
                self.ExpectedEntry('Boat', 3712, 12),
                self.ExpectedEntry('Kazoo', 3417, 17),
                self.ExpectedEntry('Tiddlywinks', 8412, 12),
                self.ExpectedEntry('Top', 523, 23),
            ))

            tree['Boat'] = self.AugIntDiv10(756)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Balloon', 2512, 12),
                self.ExpectedEntry('Boat', 756, 75),
                self.ExpectedEntry('Kazoo', 3417, 17),
                self.ExpectedEntry('Tiddlywinks', 8412, 12),
                self.ExpectedEntry('Top', 523, 23),
            ))

            tree['Tiddlywinks'] = 845
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Balloon', 2512, 12),
                self.ExpectedEntry('Boat', 756, 75),
                self.ExpectedEntry('Kazoo', 3417, 17),
                self.ExpectedEntry('Tiddlywinks', 845, 1),
                self.ExpectedEntry('Top', 523, 23),
            ))

            tree['Balloon'] = 756.3
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Balloon', 756.3, 1),
                self.ExpectedEntry('Boat', 756, 75),
                self.ExpectedEntry('Kazoo', 3417, 17),
                self.ExpectedEntry('Tiddlywinks', 845, 1),
                self.ExpectedEntry('Top', 523, 23),
            ))

            tree['Kazoo'] = self.AugIntMod100(5300)
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('Balloon', 756.3, 1),
                self.ExpectedEntry('Boat', 756, 75),
                self.ExpectedEntry('Kazoo', 5300, 12),
                self.ExpectedEntry('Tiddlywinks', 845, 1),
                self.ExpectedEntry('Top', 523, 23),
            ))

        # Test delete single node
        #
        # Creates a single node tree and then deletes that
        # single node.
        preferred_execution_order.append('test_del_single_entry')
        def test_del_single_entry(self):
            tree = AugmentedDict()
            tree['house'] = 'vacation'
            TestSupport.check_expected(tree, (
                self.ExpectedEntry('house', 'vacation', 1), ))
            del tree['house']
            TestSupport.check_expected(tree, ( ))

        preferred_execution_order.append('test_del_right_leaf')
        def test_del_right_leaf(self):
            tree = AugmentedDict()
            tree['Delaware'] = self.AugIntMod100(73658)
            tree['Ohio'] = self.AugIntMod100(87238)
            del tree['Ohio']

            expected = (
                    self.ExpectedEntry('Delaware', 73658, 58),
                )
            TestSupport.check_expected(tree, expected)

        preferred_execution_order.append('test_del_left_leaf')
        def test_del_left_leaf(self):
            tree = AugmentedDict()
            tree['Michigan'] = self.AugIntMod100(8627)
            tree['California'] = self.AugIntMod100(7835)
            del tree['California']

            expected = (
                    self.ExpectedEntry('Michigan', 8627, 27),
                )
            TestSupport.check_expected(tree, expected)

        # Test delete tree size == 5, npairs == 5
        # For all permutations, of 5 elements from a tree size of
        # 5 elements (5! == 120 permutations), creates a tree
        # of 5 elements and then removes the 5 elements in the
        # order specified by the permutation.
        preferred_execution_order.append('test_del_tree5_npairs5')
        def test_del_tree5_npairs5(self):
            TestSupport.perform_npairs_del(5, 5)

        # Test delete tree size == 7, npairs == 4
        # For all permutations, of 4 elements from a tree size of
        # 7 elements (7!/(7 - 4)! == 840 permutations), creates a
        # a tree of 7 elements and then removes the 4 elements in the
        # order specified by the permutation.
        preferred_execution_order.append('test_del_tree7_npairs4')
        def test_del_tree7_npairs4(self):
            TestSupport.perform_npairs_del(7, 4)

    class FunctionalTests(unittest.TestCase):
        def test_del_tree7_npairs7(self):
            TestSupport.perform_npairs_del(7, 7)

        def test_del_tree15_npairs3(self):
            TestSupport.perform_npairs_del(15, 3)

        def test_prandom_small(self):
            PRandomTests.perform_prandom(pass_start=0, num_passes=10000,
                    banner_every=1000, elements_max=20)

        def test_prandom_medium(self):
            PRandomTests.perform_prandom(pass_start=0, num_passes=10000,
                    banner_every=1000, elements_max=100,
                    add_ratio=0.6, del_ratio=0.2)

        def test_prandom_large(self):
            PRandomTests.perform_prandom(pass_start=0, num_passes=1000,
                    banner_every=100, elements_max=1000, ops_max=10000,
                    add_ratio=0.8, del_ratio=0.1)

    # ---- Pseudo-Random Tests ----
    class PRandomTests(unittest.TestCase):
        key_length = 8

        def test_prandom_0_1000(self):
            PRandomTests.perform_prandom(pass_start=0, num_passes=1000)

        @staticmethod
        def perform_prandom(pass_start=0, num_passes=1, verbose=False,
                elements_max=100, ops_max=500, add_ratio=0.4, del_ratio=0.4,
                banner_every=0):
            if verbose:
                print()
                print('pass_start: ', pass_start)
                print('num_passes: ', num_passes)
                print('elements_max: ', elements_max)
                print('ops_max: ', ops_max)
                print('add_ratio: ', add_ratio)
                print('del_ratio: ', del_ratio)

            if (add_ratio + del_ratio) > 1.0:
                raise ValueError('Add plus del ratio > 1.0\n'
                        '  add_ratio: %s del_ratio: %s'
                        % (add_ratio, del_ratio))

            for pass_num in range(pass_start, pass_start + num_passes):
                if verbose or ((banner_every > 0)
                        and (pass_num != pass_start)
                        and (((pass_num - pass_start) % banner_every) == 0)):
                    if pass_num - pass_start == banner_every:
                        print()
                    print('  pass: %s of %s' % (pass_num, num_passes))

                random.seed(pass_num)
                elements_max = random.randint(5, elements_max)
                operations_num = random.randint(3, ops_max)
                if verbose:
                    print('  elements_max: ', elements_max)
                    print('  operations_num: ', operations_num)

                tree = AugmentedDict()
                expected = []

                # Initially popoulate half of maximum number of elements.
                for i in range(elements_max // 2):
                    key = PRandomTests.random_key(
                            [_.key for _ in expected])
                    val = PRandomTests.random_val()
                    aug_amt = (val.augmented_val() if
                            hasattr(val, 'augmented_val') else 1)
                    if verbose:
                        print('initial add entry key: %s val: %s aug_amt: %s'
                                % (key, val, aug_amt))
                    tree[key] = val;
                    expected.append(TestSupport.ExpectedEntry(
                        key, val, aug_amt))

                # Perform the operations.
                for op_num in range(operations_num):
                    # When the tree is empty always perform an add operation.
                    force_add = True if not len(expected) else False
                    if verbose:
                        print('  op_num: %s ' % op_num, end="")

                    op_choice = random.random()
                    if force_add or op_choice < add_ratio:
                        # Add Entry
                        # Nop if max entries already exist.
                        if len(expected) < elements_max:
                            key = PRandomTests.random_key(
                                    [_.key for _ in expected])
                            val = PRandomTests.random_val()
                            aug_amt = (val.augmented_val() if
                                    hasattr(val, 'augmented_val') else 1)
                            if verbose:
                                print('add entry key: %s val: %s aug_amt: %s'
                                        % (key, val, aug_amt))
                            tree[key] = val;
                            expected.append(TestSupport.ExpectedEntry(
                                key, val, aug_amt))
                        else:
                            if verbose:
                                print('NOP')

                    elif op_choice < add_ratio + del_ratio:
                        # Delete an entry
                        idx = random.randint(0, len(expected) - 1)
                        if verbose:
                            print('Delete entry at idx: %s key: %s'
                                    % (idx, expected[idx].key))
                        del tree[expected[idx].key]
                        del expected[idx]

                    else:
                        # Update value in existing entry
                        idx = random.randint(0, len(expected) - 1)
                        key = expected[idx].key
                        val = PRandomTests.random_val()
                        aug_amt = (val.augmented_val() if
                                hasattr(val, 'augmented_val') else 1)
                        if verbose:
                            print('update entry at idx: ', idx)
                        tree[key] = val
                        expected[idx] = TestSupport.ExpectedEntry(
                                key, val, aug_amt)

                TestSupport.check_expected(tree, expected,
                        'pass: %s' % pass_num)

        @staticmethod
        def random_key(exclude=[]):
            key = ''.join(random.choice(string.digits
                + string.ascii_letters)
                for _ in range(PRandomTests.key_length))
            while key in exclude:
                key = ''.join(random.choice(string.digits
                    + string.letters) for _ in range(PRandomTests.key_length))
            return key

        @staticmethod
        def random_val():
            val = TestSupport.AugIntMod100(random.randint(-1000000, 1000000))
            return val

    class PRandomContinousTest(unittest.TestCase):
        # elements_max=100, ops_max=500, add_ratio=0.4, del_ratio=0.4,
        def test_continous(self):
            traits = [
                    {'elements_max':20},
                    {'elements_max':100},
                    {'elements_max':1000, 'add_ratio':0.7, 'del_ratio':0.2},
                ]

            pass_num = 0
            passes_each_batch = 1000
            batches_per_trait = 10
            batches_this_trait = 0
            trait_idx = 0
            print()
            while True:
                if batches_this_trait == 0:
                    print('traits: ', traits[trait_idx])
                print('  passes: %s' % pass_num, end="")

                batch_start_time = time.clock()
                PRandomTests.perform_prandom(pass_start=pass_num,
                        num_passes=passes_each_batch,
                        **traits[trait_idx])
                batch_end_time = time.clock()

                batch_time = batch_end_time - batch_start_time
                if (batch_time > 0.0):
                    print(' - %s passes/sec: %.2f'
                            % (pass_num + passes_each_batch - 1,
                                passes_each_batch / batch_time))
                else:
                    print()

                batches_this_trait += 1
                if batches_this_trait == batches_per_trait:
                    trait_idx = (trait_idx + 1) % len(traits)
                    batches_this_trait = 0
                pass_num += passes_each_batch

    # ---- Smoke Test Suite ----
    SmokeTestSuite = unittest.TestSuite()
    SmokeTestSuite.addTests(map(UnitTests, UnitTests.preferred_execution_order))
    SmokeTestSuite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        PRandomTests))

    # ---- PreSubmit Test Suite ----
    PreSubmitTestSuite = unittest.TestSuite()
    PreSubmitTestSuite.addTests(SmokeTestSuite)
    PreSubmitTestSuite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        FunctionalTests))

    # Run the command-line specified tests.  If no tests specified
    # on the command-line, then by default the tests within the
    # smoke test suite are executed.
    unittest.main(defaultTest='SmokeTestSuite')
