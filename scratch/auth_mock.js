const User = require('./models/User');

router.post('/signup', async (req, res) => {
    const user = new User(req.body);
    await user.save();
});
