#! /bin/env nu

ls | each { 
  print ([
    (ansi green)
    # '# ' 
    ($in.name | str uppercase)
    (ansi reset)
  ] | str join); 
  print ''; 
  ls $in.name | sort-by modified | get name | each {
    let file = $in | path basename
    # print (['   ', $file] | str join)
    print $file
    # head -n 4 $in | print
  }; 
  print '' 
};

();
