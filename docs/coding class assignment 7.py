import random

lowercase_letters = "goo"
digits = "0123456789"
symbols = "!"

lower, nums, syms = True, True, True

all = ""

# if lower:
all += lowercase_letters
all = all + lowercase_letters

# if nums:
all += digits
# if syms:
all +=symbols

length = 6
amount = 1

for x in range(amount):
    password = "".join(random.sample(all,length))
    print(password)

