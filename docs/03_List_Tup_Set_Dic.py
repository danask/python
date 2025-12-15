#########################################
# List is a collection which is ordered and changeable. Allows duplicate members.
# List:         ordered,    changeable,       duplicate
# Tuple:        ordered,    unchangeable,     duplicate
# Set:          unordered,  unindexed        No duplicate
# Dictionary:   ordered,    changeable       No duplicate

print ("========== List [] (array) ==============")

myList = [1, 'a', 3, 1]
print ( type(list))

print (myList)
print (myList.index('a'))
print (myList[-1])
myList.append("b")
print (myList)
myList.insert(1, 'c') # idx, obj
print (myList)
myList.pop() # stack pop (from end)
print (myList)
print (myList.count('1'), myList.count(1))

numList = []

for val in myList:
    if not (str(val).isalpha()):
        print ("I'm number {}" .format(val))
        numList.append(val)

numList.sort()
print(numList)

numList.reverse()
print(numList)

# numList.clear()
# print(numList)

myList.extend(numList)
print(myList)

#########################################
print ("========== Tuple () (enum-like, no add, no del, but fast) ==============")

menu = ("Ham", "Cheese")
print ( type(menu))


name, age, hobby = "Dan", 100, "Game"
print(name, age, hobby)

(name2, age2, hobby2) = ("Dan2", 1002, "Game2")

print(name2, age2, hobby2)



#########################################
print ("========== Set {} (HashSet-like, no dup, no order) ==============")

my_set = {1,2,3,3,3} # 3 is gone
print ( type(my_set))

my_set.add(9)
my_set.remove(1)
print(my_set)

my_hashSet = set([1, 3, 5])   # []
print(my_hashSet)

# overlapped
print(my_set & my_hashSet) 
print(my_set.intersection(my_hashSet))

print(my_set | my_hashSet) 
print(my_set.union(my_hashSet))

print(my_set - my_hashSet)
# print(my_set + my_hashSet) wrong



#########################################
print ("========== Dic {} (HashMap-like, key: value) ==============")

jsonStyle = {1:"Daniel", 2: "Angela", 3: ['a', 'b', 'c'], "test": "abc"}
print ( type(jsonStyle))

jsonStyle[4] = "add" # no add, put, append
print(jsonStyle[1])
print(jsonStyle[3][1])
print(jsonStyle.get(5)) #[5]: error
print(jsonStyle.get(5, "default value")) #[5]: error
print('a' in jsonStyle) # exist?
print(jsonStyle["test"])

# add new
jsonStyle["test2"] = "new???"
print(jsonStyle)

# del
del jsonStyle["test2"]
print(jsonStyle)

# only keys | values
print(jsonStyle.keys())
print(jsonStyle.values())
print(jsonStyle.items())
jsonStyle.clear()
print(jsonStyle)


#########################################
print ("========== Conversion ==============")

mySet = {"Ham", "Cheese"}
print (mySet, type(mySet))

myTuple = tuple(mySet)
print (myTuple, type(myTuple))

myList = list({"Ham", "Cheese"})
print (myList, type(myList))

mySet = set(myList)
print (mySet, type(mySet))



# Quiz 1.Write a Python program which accepts a sequence of comma-separated numbers from user 
# and generate a list and a tuple with those numbers. 
# Sample data : 3, 5, 7, 23
# Output :
# List : ['3', ' 5', ' 7', ' 23']
# Tuple : ('3', ' 5', ' 7', ' 23')


# Quiz 2. Reply 20 people, ID: 1 to 20, no dup, random

# -- Winners --
# Starbucks: 2
# TeamHortons: [1,8,7]

from random import *

# candidates = [1,2,3,4,5]
candidates = range(1, 21) # 1 to 20

print(type(candidates))
candidates = list(candidates)

shuffle(candidates)
winner = sample(candidates, 1)
print ("Starbucks:", winner[0])
winners = sample(candidates, 3)
print ("TeamHortons:", winner[:3])




