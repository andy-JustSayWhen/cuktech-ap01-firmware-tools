typedef unsigned char u8;
typedef unsigned int u32;

#define VA_OPEN  0xa003f448u
#define VA_CLOSE 0xa0026788u
#define VA_READ  0xa003f5f4u
#define VA_WRITE 0xa0027d94u

#define AP01_O_RDONLY 1
#define AP01_O_WRONLY_CREAT_TRUNC 38
#define AP01_MODE_0666 438
#define PAGE_RECORD_MAGIC 0x47535041u
#define PAGE_RECORD_SALT 0x6d8135c7u
#define PAGE_MASK_VALID 0x3fu
#define PAGE_MASK_DEFAULT 0x23u

typedef int (*open_fn)(const char *, int, int);
typedef int (*close_fn)(int);
typedef int (*read_fn)(int, void *, u32);
typedef int (*write_fn)(int, const void *, u32);

struct page_record
{
  u32 magic;
  u32 sequence;
  u32 mask;
  u32 check;
};

static const char page_path0[] = "/data/.ap01-page0";
static const char page_path1[] = "/data/.ap01-page1";

static int read_exact(int fd, void *target, u32 length)
{
  u8 *cursor = (u8 *)target;
  u32 done = 0u;
  while (done < length)
    {
      int amount = ((read_fn)VA_READ)(fd, cursor + done, length - done);
      if (amount <= 0 || (u32)amount > length - done)
        return 0;
      done += (u32)amount;
    }
  return 1;
}

static int write_exact(int fd, const void *source, u32 length)
{
  const u8 *cursor = (const u8 *)source;
  u32 done = 0u;
  while (done < length)
    {
      int amount = ((write_fn)VA_WRITE)(fd, cursor + done, length - done);
      if (amount <= 0 || (u32)amount > length - done)
        return 0;
      done += (u32)amount;
    }
  return 1;
}

static u32 record_check(const struct page_record *record)
{
  return record->magic ^ record->sequence ^ record->mask ^ PAGE_RECORD_SALT;
}

static int record_valid(const struct page_record *record)
{
  return record->magic == PAGE_RECORD_MAGIC
      && (record->mask & ~PAGE_MASK_VALID) == 0u
      && record->check == record_check(record);
}

static int read_record(const char *path, struct page_record *record)
{
  int fd = ((open_fn)VA_OPEN)(path, AP01_O_RDONLY, 0);
  int result;
  u8 extra;
  if (fd < 0)
    return 0;
  result = read_exact(fd, record, (u32)sizeof(*record));
  if (result && ((read_fn)VA_READ)(fd, &extra, 1u) != 0)
    result = 0;
  if (((close_fn)VA_CLOSE)(fd) < 0)
    result = 0;
  return result && record_valid(record);
}

static int invalidate_record(const char *path)
{
  int fd = ((open_fn)VA_OPEN)(path, AP01_O_WRONLY_CREAT_TRUNC, AP01_MODE_0666);
  if (fd < 0)
    return 0;
  return ((close_fn)VA_CLOSE)(fd) >= 0;
}

static int newer(u32 left, u32 right)
{
  return (int)(left - right) > 0;
}

static int current_record(
    struct page_record *record0,
    struct page_record *record1)
{
  int valid0 = read_record(page_path0, record0);
  int valid1 = read_record(page_path1, record1);
  if (valid0 && valid1)
    return newer(record1->sequence, record0->sequence) ? 1 : 0;
  if (valid0)
    return 0;
  if (valid1)
    return 1;
  return -1;
}

__attribute__((noinline, used))
u32 ap01_page_settings_load_mask(void)
{
  struct page_record record0;
  struct page_record record1;
  int current = current_record(&record0, &record1);
  if (current == 0)
    return record0.mask;
  if (current == 1)
    return record1.mask;
  return PAGE_MASK_DEFAULT;
}

__attribute__((noinline, used))
int ap01_page_settings_save_mask(u32 mask)
{
  struct page_record record0;
  struct page_record record1;
  struct page_record verify;
  struct page_record next;
  int current;
  int target;
  int fd;
  const char *path;
  int result;

  if ((mask & ~PAGE_MASK_VALID) != 0u)
    return 0;
  current = current_record(&record0, &record1);
  target = current == 0 ? 1 : 0;
  next.magic = PAGE_RECORD_MAGIC;
  next.sequence = current == 0
      ? record0.sequence + 1u
      : current == 1 ? record1.sequence + 1u : 1u;
  next.mask = mask;
  next.check = record_check(&next);
  path = target == 0 ? page_path0 : page_path1;
  fd = ((open_fn)VA_OPEN)(path, AP01_O_WRONLY_CREAT_TRUNC, AP01_MODE_0666);
  if (fd < 0)
    return 0;
  result = write_exact(fd, &next, (u32)sizeof(next));
  if (((close_fn)VA_CLOSE)(fd) < 0)
    result = 0;
  if (!result || !read_record(path, &verify))
    return 0;
  return verify.sequence == next.sequence && verify.mask == next.mask;
}

__attribute__((noinline, used))
int ap01_page_settings_reset(void)
{
  int invalid0 = invalidate_record(page_path0);
  int invalid1 = invalidate_record(page_path1);
  if (!invalid0 || !invalid1)
    return 0;
  return ap01_page_settings_save_mask(PAGE_MASK_DEFAULT);
}
