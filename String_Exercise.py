name = "Jino" # var = value (assign) cf. if 3 == 4:
age = 15 # integer

# print (type(name)) # str
# print (type(age)) # int

# print ("I am " + name + " and my age is " + str(age)) # casting
# print ("I am {0}. My age is {2}. My score is {1}." .format("Jino", 100, 15)) # 0, 1, 2
# print ("I am {name}. My age is {age}. My score is {score}." .format(name = "Jino", score = 100, age = 15)) # 0, 1, 2


# Let’s introduce myself using ‘format’
# (print("I am {1}, {0}" .format(" John ", 100)))

# hint: 
# variables: name, grade, school, hobby
# values: Jino, 8, Vancouver, computer game

# example: 
# e.g.,”I’m Daniel and in grade 8 at Vancouver school. I like playing a computer game”




phoneNumber = "A23-B56-B890" 
#  (index (0 ~ 11), character: ‘a’, ‘2’, ‘!’, ‘-’, ‘+’)

print ("length: ", len(phoneNumber)) # 12

print ("first: ", phoneNumber[0:3]) # [:3] idx: 0 to 2 (0, 1, 2) # 3 X
print ("second: ", phoneNumber[4:7]) # idx: 4 to 6 (4, 5, 6) # 7 X
print ("third: ", phoneNumber[8:12]) # [8:]

print ("index of B:", phoneNumber.index('B'))

print ("\n--------- HW #1 ----------\n")

print ("I am {0}, and my age is {1}" .format("Jino", 13))
# print ("I’m {0} and in grade {1} at {2} school. I like playing {3}" 
#         .format("Jino", 8, "Vancouver", "a computer game"))

print ("\n--------- HW #2 ----------\n")
print ("A robot was created by man. But even if I had a robot that knew everything,everything, I couldn't really say, Tell me every custom they have here and be fullyinformed. No human can solder a billion transistors on a computer processor, soyour computer needed a robot in order to be built. Instead, it is a large, open-airfarm with a robot assigned to make each turnip be all that it can be." .replace('robot', 'AI'))

print ("\n--------- HW #3 ----------\n")
