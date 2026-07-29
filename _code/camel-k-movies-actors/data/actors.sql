CREATE TABLE IF NOT EXISTS actors (
  id INTEGER NOT NULL,
  name VARCHAR(200) NOT NULL,
  character_name VARCHAR(200),
  movie_id VARCHAR(10) NOT NULL,
  PRIMARY KEY (id, movie_id)
);

DELETE FROM actors;

INSERT INTO actors (id, name, character_name, movie_id) VALUES
-- The Shawshank Redemption (tt0111161)
(1, 'Tim Robbins', 'Andy Dufresne', 'tt0111161'),
(2, 'Morgan Freeman', 'Ellis Boyd "Red" Redding', 'tt0111161'),
-- The Godfather (tt0068646)
(3, 'Marlon Brando', 'Don Vito Corleone', 'tt0068646'),
(4, 'Al Pacino', 'Michael Corleone', 'tt0068646'),
(5, 'James Caan', 'Sonny Corleone', 'tt0068646'),
-- The Godfather Part II (tt0071562)
(4, 'Al Pacino', 'Michael Corleone', 'tt0071562'),
(6, 'Robert De Niro', 'Young Vito Corleone', 'tt0071562'),
(7, 'Robert Duvall', 'Tom Hagen', 'tt0071562'),
-- The Dark Knight (tt0468569)
(8, 'Christian Bale', 'Bruce Wayne / Batman', 'tt0468569'),
(9, 'Heath Ledger', 'Joker', 'tt0468569'),
(10, 'Aaron Eckhart', 'Harvey Dent', 'tt0468569'),
(11, 'Michael Caine', 'Alfred', 'tt0468569'),
-- 12 Angry Men (tt0050083)
(12, 'Henry Fonda', 'Juror 8', 'tt0050083'),
(13, 'Lee J. Cobb', 'Juror 3', 'tt0050083'),
(14, 'Martin Balsam', 'Juror 1', 'tt0050083'),
(15, 'Jack Klugman', 'Juror 5', 'tt0050083'),
-- Schindler''s List (tt0108052)
(16, 'Liam Neeson', 'Oskar Schindler', 'tt0108052'),
(17, 'Ralph Fiennes', 'Amon Goeth', 'tt0108052'),
(18, 'Ben Kingsley', 'Itzhak Stern', 'tt0108052'),
-- The Lord of the Rings: The Return of the King (tt0167260)
(19, 'Sean Astin', 'Samwise Gamgee', 'tt0167260'),
(20, 'Viggo Mortensen', 'Aragorn', 'tt0167260'),
(21, 'Elijah Wood', 'Frodo Baggins', 'tt0167260'),
(22, 'Ian McKellen', 'Gandalf', 'tt0167260'),
-- Pulp Fiction (tt0110912)
(23, 'John Travolta', 'Vincent Vega', 'tt0110912'),
(24, 'Samuel L. Jackson', 'Jules Winnfield', 'tt0110912'),
-- Fight Club (tt0137523)
(25, 'Brad Pitt', 'Tyler Durden', 'tt0137523'),
(26, 'Edward Norton', 'The Narrator', 'tt0137523'),
(27, 'Helena Bonham Carter', 'Marla Singer', 'tt0137523'),
-- The Lord of the Rings: The Fellowship of the Ring (tt0120737)
(19, 'Sean Astin', 'Samwise Gamgee', 'tt0120737'),
(20, 'Viggo Mortensen', 'Aragorn', 'tt0120737'),
(21, 'Elijah Wood', 'Frodo Baggins', 'tt0120737'),
(22, 'Ian McKellen', 'Gandalf', 'tt0120737'),
-- Forrest Gump (tt0109830)
(28, 'Tom Hanks', 'Forrest Gump', 'tt0109830'),
(29, 'Robin Wright', 'Jenny Curran', 'tt0109830'),
(30, 'Gary Sinise', 'Lieutenant Dan Taylor', 'tt0109830'),
-- Star Wars: Episode V - The Empire Strikes Back (tt0080684)
(31, 'Mark Hamill', 'Luke Skywalker', 'tt0080684'),
(32, 'Harrison Ford', 'Han Solo', 'tt0080684'),
(33, 'Carrie Fisher', 'Princess Leia', 'tt0080684'),
-- Inception (tt1375666)
(34, 'Leonardo DiCaprio', 'Dom Cobb', 'tt1375666'),
(35, 'Tom Hardy', 'Eames', 'tt1375666'),
(36, 'Ken Watanabe', 'Saito', 'tt1375666'),
-- The Matrix (tt0133093)
(37, 'Laurence Fishburne', 'Morpheus', 'tt0133093'),
(38, 'Keanu Reeves', 'Neo', 'tt0133093'),
(39, 'Carrie-Anne Moss', 'Trinity', 'tt0133093'),
-- Goodfellas (tt0099685)
(6, 'Robert De Niro', 'James Conway', 'tt0099685'),
(4, 'Al Pacino', 'Henry Hill', 'tt0099685'),
(40, 'Joe Pesci', 'Tommy DeVito', 'tt0099685'),
-- One Flew Over the Cuckoo''s Nest (tt0073486)
(41, 'Jack Nicholson', 'R.P. McMurphy', 'tt0073486'),
(42, 'Danny DeVito', 'Martini', 'tt0073486'),
-- Se7en (tt0114369)
(25, 'Brad Pitt', 'Detective Mills', 'tt0114369'),
(2, 'Morgan Freeman', 'Detective Somerset', 'tt0114369'),
(43, 'Kevin Spacey', 'John Doe', 'tt0114369'),
-- Life is Beautiful (tt0118799)
(44, 'Roberto Benigni', 'Guido Orefice', 'tt0118799'),
(45, 'Nicoletta Braschi', 'Dora', 'tt0118799'),
-- Amélie (tt0211915)
(46, 'Audrey Tautou', 'Amélie Poulain', 'tt0211915'),
(47, 'Mathieu Kassovitz', 'Nino Quincampoix', 'tt0211915'),
-- Star Wars: Episode IV - A New Hope (tt0076759)
(31, 'Mark Hamill', 'Luke Skywalker', 'tt0076759'),
(32, 'Harrison Ford', 'Han Solo', 'tt0076759'),
(33, 'Carrie Fisher', 'Princess Leia', 'tt0076759'),
-- Toy Story (tt0110357)
(28, 'Tom Hanks', 'Woody', 'tt0110357'),
(48, 'Tim Allen', 'Buzz Lightyear', 'tt0110357'),
-- Saving Private Ryan (tt0120815)
(28, 'Tom Hanks', 'Captain Miller', 'tt0120815'),
(49, 'Edward Burns', 'Private Reiben', 'tt0120815'),
-- Terminator 2: Judgment Day (tt0103064)
(50, 'Arnold Schwarzenegger', 'The Terminator', 'tt0103064'),
(51, 'Linda Hamilton', 'Sarah Connor', 'tt0103064'),
-- Raiders of the Lost Ark (tt0082971)
(32, 'Harrison Ford', 'Indiana Jones', 'tt0082971'),
(52, 'Karen Allen', 'Marion Ravenwood', 'tt0082971'),
-- Requiem for a Dream (tt0180093)
(53, 'Jared Leto', 'Harry Goldfarb', 'tt0180093'),
(54, 'Jennifer Connelly', 'Marion Silver', 'tt0180093'),
-- The Departed (tt0407887)
(34, 'Leonardo DiCaprio', 'Billy Costigan', 'tt0407887'),
(41, 'Jack Nicholson', 'Frank Costello', 'tt0407887'),
(55, 'Matt Damon', 'Colin Sullivan', 'tt0407887'),
-- Psycho (tt0054215)
(56, 'Anthony Perkins', 'Norman Bates', 'tt0054215'),
(57, 'Janet Leigh', 'Marion Crane', 'tt0054215'),
-- Léon: The Professional (tt0110413)
(58, 'Jean Reno', 'Léon', 'tt0110413'),
(59, 'Natalie Portman', 'Mathilda', 'tt0110413'),
(60, 'Gary Oldman', 'Stansfield', 'tt0110413'),
-- Princess Mononoke (tt0119698)
(61, 'Yôji Matsuda', 'Ashitaka', 'tt0119698'),
(62, 'Yuriko Ishida', 'San', 'tt0119698'),
-- Memento (tt0209144)
(63, 'Guy Pearce', 'Leonard Shelby', 'tt0209144'),
(64, 'Joe Pantoliano', 'John Edward Gammell', 'tt0209144'),
-- The Green Mile (tt0120586)
(28, 'Tom Hanks', 'Paul Edgecomb', 'tt0120586'),
(65, 'Michael Clarke Duncan', 'John Coffey', 'tt0120586'),
-- The Usual Suspects (tt0114814)
(43, 'Kevin Spacey', 'Roger Kint', 'tt0114814'),
(66, 'Gabriel Byrne', 'Dean Keaton', 'tt0114814'),
-- Pirates of the Caribbean (tt0325980)
(67, 'Johnny Depp', 'Jack Sparrow', 'tt0325980'),
(68, 'Orlando Bloom', 'Will Turner', 'tt0325980'),
(69, 'Keira Knightley', 'Elizabeth Swann', 'tt0325980'),
-- The Pianist (tt0253474)
(70, 'Adrien Brody', 'Wladyslaw Szpilman', 'tt0253474'),
(71, 'Thomas Kretschmann', 'Captain Wilm Hosenfeld', 'tt0253474'),
-- Gladiator (tt0172495)
(72, 'Russell Crowe', 'Maximus Decimus Meridius', 'tt0172495'),
(73, 'Joaquin Phoenix', 'Commodus', 'tt0172495'),
(74, 'Connie Nielsen', 'Lucilla', 'tt0172495'),
-- City of God (tt0317248)
(75, 'Alexandre Rodrigues', 'Rocket', 'tt0317248'),
(76, 'Leandro Firmino', 'Li''l Zé', 'tt0317248'),
-- Casablanca (tt0034583)
(77, 'Humphrey Bogart', 'Rick Blaine', 'tt0034583'),
(78, 'Ingrid Bergman', 'Ilsa Lund', 'tt0034583'),
(79, 'Claude Rains', 'Captain Renault', 'tt0034583'),
-- The Nightmare Before Christmas (tt0106694)
(80, 'Chris Sarandon', 'Jack Skellington (speaking)', 'tt0106694'),
(81, 'Danny Elfman', 'Jack Skellington (singing)', 'tt0106694'),
-- Life of Pi (tt0454876)
(82, 'Suraj Sharma', 'Pi Patel', 'tt0454876'),
(83, 'Irrfan Khan', 'Adult Pi', 'tt0454876'),
-- Jurassic Park (tt0107290)
(84, 'Sam Neill', 'Dr. Alan Grant', 'tt0107290'),
(85, 'Laura Dern', 'Dr. Ellie Sattler', 'tt0107290'),
(86, 'Jeff Goldblum', 'Dr. Ian Malcolm', 'tt0107290'),
-- Back to the Future (tt0088763)
(87, 'Michael J. Fox', 'Marty McFly', 'tt0088763'),
(88, 'Christopher Lloyd', 'Dr. Emmett Brown', 'tt0088763'),
-- Dr. Strangelove (tt0057012)
(89, 'Peter Sellers', 'Dr. Strangelove / President Muffley', 'tt0057012'),
(90, 'George C. Scott', 'General Buck Turgidson', 'tt0057012'),
-- Inglourious Basterds (tt0361748)
(25, 'Brad Pitt', 'Lt. Aldo Raine', 'tt0361748'),
(91, 'Christoph Waltz', 'Col. Hans Landa', 'tt0361748'),
(92, 'Mélanie Laurent', 'Shosanna Dreyfus', 'tt0361748'),
-- Taxi Driver (tt0075314)
(6, 'Robert De Niro', 'Travis Bickle', 'tt0075314'),
(93, 'Jodie Foster', 'Iris Steensma', 'tt0075314'),
(94, 'Cybill Shepherd', 'Betsy', 'tt0075314'),
-- Eternal Sunshine of the Spotless Mind (tt0338013)
(95, 'Jim Carrey', 'Joel Barish', 'tt0338013'),
(96, 'Kate Winslet', 'Clementine Kruczynski', 'tt0338013'),
-- Titanic (tt0120338)
(34, 'Leonardo DiCaprio', 'Jack Dawson', 'tt0120338'),
(96, 'Kate Winslet', 'Rose DeWitt Bukater', 'tt0120338'),
-- Grave of the Fireflies (tt0095327)
(97, 'Tsutomu Tatsumi', 'Seita', 'tt0095327'),
(98, 'Ayano Shiraishi', 'Setsuko', 'tt0095327'),
-- Seven Samurai (tt0047478)
(99, 'Toshirô Mifune', 'Kikuchiyo', 'tt0047478'),
(100, 'Takashi Shimura', 'Kambei Shimada', 'tt0047478'),
-- The Shining (tt0081505)
(41, 'Jack Nicholson', 'Jack Torrance', 'tt0081505'),
(101, 'Shelley Duvall', 'Wendy Torrance', 'tt0081505');