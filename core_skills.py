import random
rand_list = [random.randint(1,20) for i in range(10)]

print(f"random list: {rand_list}")
list_comprehension_below_10 = [ x for x in rand_list if x < 10]
print("less then 10", list_comprehension_below_10)
list_comprehension_below_10 = list(filter(lambda x: x < 10, rand_list))
print("less then 10 using filters", list_comprehension_below_10)
