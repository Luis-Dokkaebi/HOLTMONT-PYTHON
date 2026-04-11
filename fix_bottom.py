with open("index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Re-insert the missing <div class="card border-0 shadow-sm"><div class="card-body"> that were wrapping the bottom part?
# Wait! In the original code before modification, it was:
# <div class="col-12">
#     <div class="card border-0 shadow-sm">
#         <div class="card-header bg-dark text-white border-0 pt-3 ps-3 d-flex justify-content-between align-items-center">...</div>
#         <div class="card-body">
#             <div class="row mb-4"> ... this is the part I moved ... </div>
#             <!-- Multimedia Section (Merged) -->
#             ...

# My script moved the header and the `row mb-4`. But it left the Multimedia Section inside `<div class="col-12">`
# without the `<div class="card border-0 shadow-sm">` and `<div class="card-body">`.
# Let's see how I can wrap the remainder back.

# Let's restore the backup and do it correctly.
